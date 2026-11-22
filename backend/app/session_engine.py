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

Voting: `vote()` is the one path for every Participant's Vote (Humans via the
hub, AI Agents via their runner). The Voting Phase ends early once every
Participant in `_Run.present` (connected Humans + AI Agents) has voted. At its
end, everyone who did not vote is written as an Abstention, or as `missing`
if they are no longer present (a Dropout). After the last Round, the pure
`vote_tally.tally` gives the Result.
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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import CONDITIONS, Config
from .persistence import messages, participants, rounds, sessions, votes
from .vote_tally import ABSTENTION, MISSING, VOTE, Ballot, Result, round_summary, tally

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
    phase_over: asyncio.Event = field(default_factory=asyncio.Event)  # set = Phase over (early or at deadline)
    task: asyncio.Task | None = None
    labels: dict[int, str] = field(default_factory=dict)  # participant id -> Player Label letter
    present: set[int] = field(default_factory=set)  # ids still taking part: connected Humans + AI Agents
    voted: set[int] = field(default_factory=set)  # ids that voted in the current Voting Phase


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
                    # Dropouts during an active Session (marking, `incomplete`): ticket #16.
                    # Already here: they stop counting for the early end of voting.
                    run = self._runs.get(participant.room_code)
                    if run is not None:
                        run.present.discard(participant.id)
                        self._end_voting_if_all_voted(run)
                    return
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
                everyone = (
                    await conn.execute(
                        select(participants.c.id, participants.c.player_label).where(
                            participants.c.session_id == session.id
                        )
                    )
                ).all()
            run = _Run(session_id=session.id)
            run.labels = {row.id: row.player_label for row in everyone}
            run.present = set(run.labels)
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
        run.voted = set()
        await self._enter_phase(room_code, run, round_number, VOTING, self._config.timings.voting_seconds)
        self._end_voting_if_all_voted(run)  # e.g. nobody is present any more
        await self._wait_phase(run)
        run.phase_over.set()  # closes the ballot box: `vote()` refuses from here on
        ended = _now()
        # Whoever did not vote: an Abstention if still present, else missing (Dropout).
        # ON CONFLICT DO NOTHING keeps a row already written (e.g. by #16 at dropout).
        absent = [
            {
                "session_id": run.session_id,
                "round_number": round_number,
                "participant_id": pid,
                "kind": ABSTENTION if pid in run.present else MISSING,
                "cast_at": ended,
            }
            for pid in run.labels
            if pid not in run.voted
        ]
        async with self._db.begin() as conn:
            if absent:
                await conn.execute(pg_insert(votes).values(absent).on_conflict_do_nothing())
            ballots = await self._ballots(conn, run, round_number)
            await conn.execute(
                update(rounds)
                .where(rounds.c.session_id == run.session_id, rounds.c.round_number == round_number)
                .values(voting_end=ended, vote_results=round_summary(sorted(run.labels.values()), ballots))
            )
        log.info(
            "Session %s: Round %d voting closed (%d of %d voted)", room_code, round_number, len(run.voted), len(run.labels)
        )

    async def _ballots(self, conn, run: _Run, round_number: int | None = None) -> list[Ballot]:
        """Stored Votes of this Session (one Round, or all Rounds) as tally input."""
        query = select(votes.c.round_number, votes.c.participant_id, votes.c.kind, votes.c.target_participant).where(
            votes.c.session_id == run.session_id
        )
        if round_number is not None:
            query = query.where(votes.c.round_number == round_number)
        return [
            Ballot(row.round_number, run.labels[row.participant_id], row.kind, run.labels.get(row.target_participant))
            for row in (await conn.execute(query)).all()
        ]

    async def _finish(self, room_code: str, run: _Run) -> None:
        """Compute the Result from both Rounds, store it, mark the Session
        completed and send everyone the `result` frame."""
        async with self._db.begin() as conn:
            result = tally(sorted(run.labels.values()), await self._ballots(conn, run))
            await conn.execute(
                update(sessions)
                .where(sessions.c.id == run.session_id)
                .values(
                    status="completed",
                    completed_at=func.now(),
                    last_activity=func.now(),
                    decision_maker=result.decision_maker,
                    decided_by_tiebreak=result.decided_by_tiebreak,
                )
            )
            types = None
            if self._config.reveal_identities_at_end:
                rows = await conn.execute(
                    select(participants.c.player_label, participants.c.type).where(
                        participants.c.session_id == run.session_id
                    )
                )
                types = {row.player_label: row.type for row in rows}
        run.round, run.phase, run.deadline = None, None, None
        await self._emit(Event(room_code, self._result_frame(result, types)))
        log.info(
            "Session %s completed: Decision Maker Player %s%s",
            room_code,
            result.decision_maker,
            " (tie-break)" if result.decided_by_tiebreak else "",
        )

    @staticmethod
    def _result_frame(result: Result, types: dict[str, str] | None = None) -> dict[str, Any]:
        # Player Labels and counts only. `types` (letter -> "human" | "ai") is passed
        # only when `reveal_identities_at_end` is on: the one frame that may carry them.
        frame = {
            "type": "result",
            "counts": {f"Player {label}": n for label, n in sorted(result.counts.items())},
            "decision_maker": f"Player {result.decision_maker}",
        }
        if types is not None:
            frame["types"] = {f"Player {label}": kind for label, kind in sorted(types.items())}
        return frame

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
            "player_labels": [f"Player {label}" for label in sorted(run.labels.values())],  # the ballot
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

    # --- Voting ----------------------------------------------------------

    async def vote(self, participant: JoinedParticipant, target: Any) -> None:
        """Record one Vote for any Player Label (self included), once per Round.

        The one path for Humans and AI Agents alike. Only the voter hears back
        (`vote_recorded`); nobody learns counts or choices before the Result.
        Rejections: `vote_closed`, `bad_vote` (unknown label), `already_voted`.
        """
        run = self._runs.get(participant.room_code)
        if run is None or run.phase != VOTING or run.phase_over.is_set() or participant.id not in run.present:
            await self._reject(participant, "vote_closed")
            return
        letter = target.removeprefix("Player ").strip() if isinstance(target, str) else None
        target_id = next((pid for pid, label in run.labels.items() if label == letter), None)
        if target_id is None:
            await self._reject(participant, "bad_vote")
            return
        if participant.id in run.voted:
            await self._reject(participant, "already_voted")
            return
        run.voted.add(participant.id)  # claimed before any await: no double Vote under races
        round_number, cast_at = run.round, _now()
        async with self._db.begin() as conn:
            await conn.execute(
                insert(votes).values(
                    session_id=participant.session_id,
                    round_number=round_number,
                    participant_id=participant.id,
                    target_participant=target_id,
                    kind=VOTE,
                    cast_at=cast_at,
                )
            )
            await conn.execute(
                update(participants).where(participants.c.id == participant.id).values(last_activity=cast_at)
            )
            await conn.execute(
                update(sessions).where(sessions.c.id == participant.session_id).values(last_activity=cast_at)
            )
        await self._emit(
            Event(participant.room_code, {"type": "vote_recorded", "round": round_number}, recipient=participant.id)
        )
        self._end_voting_if_all_voted(run)

    @staticmethod
    def _end_voting_if_all_voted(run: _Run) -> None:
        """End the Voting Phase early once every present Participant has voted."""
        if run.phase == VOTING and run.present <= run.voted:
            run.phase_over.set()

    async def _reject(self, participant: JoinedParticipant, reason: str) -> None:
        await self._emit(Event(participant.room_code, {"type": "error", "reason": reason}, recipient=participant.id))


def _human_slots(condition: str) -> int:
    """Human slots of the Condition the Session was created under (not today's config)."""
    return CONDITIONS[condition][0]
