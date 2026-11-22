"""Session engine: owns the Session lifecycle.

It knows nothing about sockets. Callers (the realtime hub, the REST API) call
its methods; it changes state in PostgreSQL and emits `Event`s to subscribers.
Event payloads are wire-safe: they carry Player Labels only, never a
Participant's type (Blind Condition).

Join is two steps so the hub can register the socket in between:
`join()` reserves a slot and a Player Label, `connected()` announces it
(and is where the Session will auto-start once all Human slots are filled).
`disconnected()` frees the slot while the Session is still waiting.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import CONDITIONS, Config
from .persistence import participants, sessions

log = logging.getLogger(__name__)

PLAYER_LABELS = ("A", "B", "C")  # every Session has exactly three Participants


class JoinRefused(Exception):
    """A Human cannot join. `reason` is one of: not_found, full, active, completed, expired."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SessionNotFound(Exception):
    pass


@dataclass(frozen=True)
class JoinedParticipant:
    """What the hub needs to route frames. Deliberately has no `type` field."""

    id: int
    session_id: int
    room_code: str
    player_label: str


@dataclass(frozen=True)
class Event:
    """Something every connected Participant of a Session (or just one) must hear.

    `recipient` is a participant id, or None for everyone in the Session.
    `payload` is a JSON-safe dict with a `type`, sent as-is to browsers.
    """

    room_code: str
    payload: dict[str, Any]
    recipient: int | None = None


Subscriber = Callable[[Event], Awaitable[None]]


@dataclass
class _Locks:
    by_room: dict[str, asyncio.Lock] = field(default_factory=dict)

    def get(self, room_code: str) -> asyncio.Lock:
        return self.by_room.setdefault(room_code, asyncio.Lock())


class SessionEngine:
    def __init__(self, db: AsyncEngine, config: Config):
        self._db = db
        self._config = config
        self._subscribers: list[Subscriber] = []
        self._locks = _Locks()  # serialise joins/leaves per Session (single process)

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    async def _emit(self, event: Event) -> None:
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not break the Session
                log.exception("Event subscriber failed")

    # --- Session creation and lookup -------------------------------------

    async def create_session(self) -> str:
        """Create a `waiting` Session under the active Condition; return its Room Code."""
        room_code = secrets.token_urlsafe(9)  # 12 URL-safe chars, ~72 bits: not enumerable
        async with self._db.begin() as conn:
            await conn.execute(
                insert(sessions).values(room_code=room_code, condition=self._config.condition.name, status="waiting")
            )
        log.info("Created Session %s (condition=%s)", room_code, self._config.condition.name)
        return room_code

    async def public_state(self, room_code: str) -> dict[str, Any]:
        """Status and Player Labels present. Never Participant types."""
        async with self._db.connect() as conn:
            session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
            if session is None:
                raise SessionNotFound(room_code)
            labels = (
                await conn.execute(
                    select(participants.c.player_label)
                    .where(participants.c.session_id == session.id, participants.c.dropped_out_at.is_(None))
                    .order_by(participants.c.player_label)
                )
            ).scalars().all()
        return {
            "room_code": room_code,
            "status": session.status,
            "round": None,  # set by the Round runner (ticket #12+)
            "phase": None,
            "phase_deadline": None,
            "player_labels": [f"Player {label}" for label in labels],
        }

    # --- Waiting Room ----------------------------------------------------

    async def join(self, room_code: str) -> JoinedParticipant:
        """Reserve a Human slot with a random unused Player Label, or raise JoinRefused."""
        async with self._locks.get(room_code):
            async with self._db.begin() as conn:
                session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
                if session is None:
                    raise JoinRefused("not_found")
                if session.status != "waiting":
                    raise JoinRefused(session.status)  # active | completed | expired
                used = set(
                    (
                        await conn.execute(
                            select(participants.c.player_label).where(participants.c.session_id == session.id)
                        )
                    ).scalars()
                )
                if len(used) >= _human_slots(session.condition):
                    raise JoinRefused("full")
                label = random.choice([letter for letter in PLAYER_LABELS if letter not in used])
                participant_id = (
                    await conn.execute(
                        insert(participants)
                        .values(session_id=session.id, player_label=label, type="human")
                        .returning(participants.c.id)
                    )
                ).scalar_one()
                await conn.execute(
                    update(sessions).where(sessions.c.id == session.id).values(last_activity=func.now())
                )
        log.info("Human joined Session %s as Player %s", room_code, label)
        return JoinedParticipant(id=participant_id, session_id=session.id, room_code=room_code, player_label=label)

    async def connected(self, participant: JoinedParticipant) -> None:
        """The joiner's socket is registered; tell them their label and everyone the slot count."""
        await self._emit(
            Event(
                participant.room_code,
                {"type": "joined", "player_label": f"Player {participant.player_label}"},
                recipient=participant.id,
            )
        )
        await self._emit_waiting(participant.room_code, participant.session_id)

    async def disconnected(self, participant: JoinedParticipant) -> None:
        """A Human's socket closed. Before the start this frees their slot."""
        async with self._locks.get(participant.room_code):
            async with self._db.begin() as conn:
                status = (
                    await conn.execute(select(sessions.c.status).where(sessions.c.id == participant.session_id))
                ).scalar_one_or_none()
                if status != "waiting":
                    return  # Dropouts during an active Session: ticket #16
                await conn.execute(delete(participants).where(participants.c.id == participant.id))
                await conn.execute(
                    update(sessions).where(sessions.c.id == participant.session_id).values(last_activity=func.now())
                )
        log.info("Player %s left Session %s before the start", participant.player_label, participant.room_code)
        await self._emit_waiting(participant.room_code, participant.session_id)

    async def _emit_waiting(self, room_code: str, session_id: int) -> None:
        async with self._db.connect() as conn:
            condition = (
                await conn.execute(select(sessions.c.condition).where(sessions.c.id == session_id))
            ).scalar_one()
            filled = (
                await conn.execute(
                    select(func.count()).select_from(participants).where(participants.c.session_id == session_id)
                )
            ).scalar_one()
        await self._emit(Event(room_code, {"type": "waiting", "filled": filled, "total": _human_slots(condition)}))


def _human_slots(condition: str) -> int:
    """Human slots of the Condition the Session was created under (not today's config)."""
    return CONDITIONS[condition][0]
