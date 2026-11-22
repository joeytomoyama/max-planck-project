"""Session engine: owns the Session lifecycle and every server-side timer.

It knows nothing about sockets. Callers (the realtime hub, the REST API) call
its methods; it changes state in PostgreSQL and emits `Event`s to subscribers.
Event payloads are wire-safe: they carry Player Labels only, never a
Participant's type (Blind Condition).

Join is two steps so the hub can register the socket in between:
`join()` reserves a slot and a Player Label, `connected()` announces it and
starts the Session once all Human slots are filled (the same transition as
`start()`, the manual start endpoint). `disconnected()` frees the slot while
the Session is still waiting.

Once active, one asyncio task per Session (`_run_session`) walks the Rounds:
each Round is a Discussion Phase then a Voting Phase. Every Phase goes through
`_enter_phase` (sets the server deadline, emits a `phase` frame) and
`_wait_phase` (sleeps until the deadline, or until `_Run.phase_over` is set to
end it early, e.g. once everyone has voted).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import CONDITIONS, Config
from .persistence import messages, participants, rounds, sessions

log = logging.getLogger(__name__)

PLAYER_LABELS = ("A", "B", "C")  # every Session has exactly three Participants
MAX_CHAT_LENGTH = 500  # characters; longer messages are cut, not rejected

DISCUSSION = "discussion"
VOTING = "voting"


class JoinRefused(Exception):
    """A Human cannot join. `reason` is one of: not_found, full, active, completed, expired."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SessionNotFound(Exception):
    pass


class NotWaiting(Exception):
    """`start()` on a Session that has already left the Waiting Room."""


@dataclass(frozen=True)
class JoinedParticipant:
    """What the hub needs to route frames. Deliberately has no `type` field.

    The AI Agent runner (#14) uses the same handle to chat and vote, so AI
    Agent messages take exactly the same path as Human ones.
    """

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


@dataclass
class _Run:
    """Live state of an active Session (single process; the DB holds the record)."""

    session_id: int
    round: int | None = None
    phase: str | None = None
    deadline: datetime | None = None
    phase_over: asyncio.Event = field(default_factory=asyncio.Event)  # set to end the Phase early
    task: asyncio.Task | None = None


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁠-⁩﻿]")


def sanitize_chat(text: Any) -> str | None:
    """Plain-text chat: control and invisible formatting characters removed
    (line breaks become spaces), trimmed, capped at MAX_CHAT_LENGTH.
    Returns None when nothing is left (the message is rejected)."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"[\t\n\r\v\f]", " ", text)
    text = _CONTROL_CHARS.sub("", text).strip()
    text = text[:MAX_CHAT_LENGTH].rstrip()
    return text or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionEngine:
    def __init__(self, db: AsyncEngine, config: Config):
        self._db = db
        self._config = config
        self._subscribers: list[Subscriber] = []
        self._locks = _Locks()  # serialise joins/leaves/start per Session (single process)
        self._runs: dict[str, _Run] = {}  # room_code -> live state of active Sessions

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    async def _emit(self, event: Event) -> None:
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not break the Session
                log.exception("Event subscriber failed")

    async def shutdown(self) -> None:
        """Cancel every Session's timer task (app shutdown)."""
        tasks = [run.task for run in self._runs.values() if run.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

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
        """Status, Round, Phase, deadline and Player Labels present. Never Participant types."""
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
        run = self._runs.get(room_code)
        return {
            "room_code": room_code,
            "status": session.status,
            "round": run.round if run else None,
            "phase": run.phase if run else None,
            "phase_deadline": run.deadline.isoformat() if run and run.deadline else None,
            "player_labels": [f"Player {label}" for label in labels],
        }

    async def ensure_exists(self, room_code: str) -> None:
        async with self._db.connect() as conn:
            found = (
                await conn.execute(select(sessions.c.id).where(sessions.c.room_code == room_code))
            ).scalar_one_or_none()
        if found is None:
            raise SessionNotFound(room_code)

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
        """The joiner's socket is registered: tell them their label and everyone the
        slot count, then start the Session if this filled the last Human slot."""
        await self._emit(
            Event(
                participant.room_code,
                {"type": "joined", "player_label": f"Player {participant.player_label}"},
                recipient=participant.id,
            )
        )
        run = self._runs.get(participant.room_code)
        if run is not None and run.phase is not None:
            # Reserved a slot before the start but connected just after it: catch up.
            await self._emit(Event(participant.room_code, self._phase_frame(run), recipient=participant.id))
            return
        await self._emit_waiting(participant.room_code, participant.session_id)
        try:
            await self.start(participant.room_code, only_when_full=True)
        except (NotWaiting, SessionNotFound):
            pass

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

    # --- Start -----------------------------------------------------------

    async def start(self, room_code: str, *, only_when_full: bool = False) -> None:
        """waiting -> active: add AI Agents for the Condition's AI slots and run Round 1.

        The manual start endpoint calls this directly; `connected()` calls it with
        `only_when_full` so it fires once every Human slot is taken.
        Raises SessionNotFound, or NotWaiting when the Session is not waiting.
        """
        async with self._locks.get(room_code):
            async with self._db.begin() as conn:
                session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
                if session is None:
                    raise SessionNotFound(room_code)
                if session.status != "waiting":
                    raise NotWaiting(room_code)
                used = set(
                    (
                        await conn.execute(
                            select(participants.c.player_label).where(participants.c.session_id == session.id)
                        )
                    ).scalars()
                )
                humans, ais = CONDITIONS[session.condition]
                if only_when_full and len(used) < humans:
                    return
                free = [letter for letter in PLAYER_LABELS if letter not in used]
                random.shuffle(free)
                for label in free[:ais]:
                    await conn.execute(
                        insert(participants).values(session_id=session.id, player_label=label, type="ai")
                    )
                await conn.execute(
                    update(sessions)
                    .where(sessions.c.id == session.id)
                    .values(status="active", last_activity=func.now())
                )
            run = _Run(session_id=session.id)
            self._runs[room_code] = run
            run.task = asyncio.create_task(self._run_session(room_code, run), name=f"session-{room_code}")
        log.info("Session %s started", room_code)

    # --- Rounds and Phases ----------------------------------------------

    async def _run_session(self, room_code: str, run: _Run) -> None:
        try:
            for round_number in range(1, self._config.number_of_rounds + 1):
                await self._discussion_phase(room_code, run, round_number)
                await self._voting_phase(room_code, run, round_number)
            await self._finish(room_code, run)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - log; a crashed timer must not take the app down
            log.exception("Session %s runner failed", room_code)
        finally:
            self._runs.pop(room_code, None)

    async def _discussion_phase(self, room_code: str, run: _Run, round_number: int) -> None:
        start = await self._enter_phase(room_code, run, round_number, DISCUSSION, self._config.timings.discussion_seconds)
        async with self._db.begin() as conn:
            await conn.execute(
                insert(rounds).values(session_id=run.session_id, round_number=round_number, discussion_start=start)
            )
        await self._wait_phase(run)
        async with self._db.begin() as conn:
            await conn.execute(
                update(rounds)
                .where(rounds.c.session_id == run.session_id, rounds.c.round_number == round_number)
                .values(discussion_end=_now())
            )

    async def _voting_phase(self, room_code: str, run: _Run, round_number: int) -> None:
        # Ticket #13: accept Votes, end early once every connected Participant
        # has voted (set run.phase_over), record Abstentions at the deadline.
        await self._enter_phase(room_code, run, round_number, VOTING, self._config.timings.voting_seconds)
        await self._wait_phase(run)
        async with self._db.begin() as conn:
            await conn.execute(
                update(rounds)
                .where(rounds.c.session_id == run.session_id, rounds.c.round_number == round_number)
                .values(voting_end=_now())
            )

    async def _finish(self, room_code: str, run: _Run) -> None:
        # Ticket #13: compute the Result (Decision Maker) and emit a `result` frame.
        async with self._db.begin() as conn:
            await conn.execute(
                update(sessions)
                .where(sessions.c.id == run.session_id)
                .values(status="completed", completed_at=func.now(), last_activity=func.now())
            )
        run.round, run.phase, run.deadline = None, None, None
        await self._emit(Event(room_code, {"type": "closed", "reason": "completed"}))
        log.info("Session %s completed", room_code)

    async def _enter_phase(self, room_code: str, run: _Run, round_number: int, phase: str, seconds: float) -> datetime:
        start = _now()
        run.round, run.phase, run.deadline = round_number, phase, start + timedelta(seconds=seconds)
        run.phase_over = asyncio.Event()
        await self._emit(Event(room_code, self._phase_frame(run)))
        log.info("Session %s: Round %d %s Phase until %s", room_code, round_number, phase, run.deadline.isoformat())
        return start

    @staticmethod
    async def _wait_phase(run: _Run) -> None:
        """Sleep until the Phase deadline, or until something sets `run.phase_over`."""
        remaining = (run.deadline - _now()).total_seconds()
        try:
            await asyncio.wait_for(run.phase_over.wait(), timeout=max(remaining, 0))
        except asyncio.TimeoutError:
            pass

    @staticmethod
    def _phase_frame(run: _Run) -> dict[str, Any]:
        # `server_time` lets clients correct for clock skew when counting down.
        return {
            "type": "phase",
            "round": run.round,
            "phase": run.phase,
            "deadline": run.deadline.isoformat(),
            "server_time": _now().isoformat(),
        }

    # --- Chat ------------------------------------------------------------

    async def chat(self, participant: JoinedParticipant, text: Any) -> None:
        """Store and broadcast a chat message. Only during a Discussion Phase.

        The broadcast carries the Player Label, text and time only. A rejected
        message gets an `error` frame back to the sender alone.
        """
        run = self._runs.get(participant.room_code)
        if run is None or run.phase != DISCUSSION:
            await self._reject(participant, "chat_closed")
            return
        clean = sanitize_chat(text)
        if clean is None:
            await self._reject(participant, "empty_message")
            return
        sent_at = _now()
        async with self._db.begin() as conn:
            await conn.execute(
                insert(messages).values(
                    session_id=participant.session_id,
                    round_number=run.round,
                    phase=run.phase,
                    participant_id=participant.id,
                    text=clean,
                    sent_at=sent_at,
                )
            )
            await conn.execute(
                update(participants).where(participants.c.id == participant.id).values(last_activity=sent_at)
            )
            await conn.execute(
                update(sessions).where(sessions.c.id == participant.session_id).values(last_activity=sent_at)
            )
        await self._emit(
            Event(
                participant.room_code,
                {
                    "type": "chat",
                    "player_label": f"Player {participant.player_label}",
                    "text": clean,
                    "sent_at": sent_at.isoformat(),
                },
            )
        )

    async def _reject(self, participant: JoinedParticipant, reason: str) -> None:
        await self._emit(Event(participant.room_code, {"type": "error", "reason": reason}, recipient=participant.id))


def _human_slots(condition: str) -> int:
    """Human slots of the Condition the Session was created under (not today's config)."""
    return CONDITIONS[condition][0]
