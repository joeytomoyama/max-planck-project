"""Session engine: owns the Session lifecycle and every server-side timer.

It knows nothing about sockets. Callers (the realtime hub, the REST API) call
its methods; it changes state in PostgreSQL and emits `Event`s to subscribers.
Event payloads are wire-safe: they carry Player Labels only, never a
Participant's type (Blind Condition).

Join is two steps so the hub can register the socket in between:
`join()` reserves a slot and a Player Label, `connected()` announces it and
starts the Session once all Human slots are filled (the same transition as
`start()`, the manual start endpoint). `disconnected()` frees the slot while
the Session is still waiting; during an active Session it makes the Human a
Dropout (`_drop_out`). `expire_inactive()` expires Sessions left without
activity (background sweeper plus a lazy check before every lookup).

Once active, one asyncio task per Session (`_run_session`) walks the Rounds:
each Round is a Discussion Phase then a Voting Phase. Every Phase goes through
`_enter_phase` (sets the server deadline, emits a `phase` frame) and
`_wait_phase` (sleeps until the deadline, or until `_Run.phase_over` is set to
end it early, e.g. once everyone has voted).

Voting: `vote()` is the one path for every Participant's Vote (Humans via the
hub, AI Agents via their runner). The Voting Phase ends early once every
Participant in `_Run.present` (connected Humans + AI Agents) has voted. At its
end, everyone who did not vote is written as an Abstention, or as `missing`
if they were no longer present at the close (a Dropout). Storing a Vote and
closing the ballot box take the same per-Session lock (`_Run.ballot_box`), so
an acknowledged Vote is always in the Round's results. After the last Round, the pure
`vote_tally.tally` gives the Result.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
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

from .config import CONDITIONS, Condition, Config
from .persistence import (
    ACTIVE,
    AI,
    COMPLETED,
    EXPIRED,
    HUMAN,
    WAITING,
    messages,
    participants,
    rounds,
    sessions,
    votes,
)
from .vote_tally import ABSTENTION, MISSING, VOTE, Ballot, Result, round_summary, tally

log = logging.getLogger(__name__)

PLAYER_LABELS = ("A", "B", "C")  # every Session has exactly three Participants
MAX_CHAT_LENGTH = 500  # characters; longer messages are cut, not rejected

DISCUSSION = "discussion"
VOTING = "voting"


class PlayerLabel:
    """The one place that turns a stored letter ("B") into the wire form
    ("Player B") and back. The database and `_Run.labels` hold letters."""

    PREFIX = "Player "

    @staticmethod
    def format(letter: str) -> str:
        return PlayerLabel.PREFIX + letter

    @staticmethod
    def parse(label: Any) -> str | None:
        """The letter of "Player B" (or of a bare "B"); None for a non-string."""
        return label.removeprefix(PlayerLabel.PREFIX).strip() if isinstance(label, str) else None


class JoinRefused(Exception):
    """A Human cannot join. `reason` is one of: not_found, full, active, completed, expired."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SessionNotFound(Exception):
    pass


class NotWaiting(Exception):
    """`start()` on a Session that has already left the Waiting Room."""


class SessionExpired(Exception):
    """The Session expired after inactivity; REST refuses it (410)."""


class WrongResearcherToken(Exception):
    """A Researcher-only request without the Session's Researcher token, or with a wrong one."""


@dataclass(frozen=True)
class CreatedSession:
    """`researcher_token` is the only copy: just its hash is stored. It goes to the
    Researcher who created the Session and never into the share link."""

    room_code: str
    researcher_token: str


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
    # Held while a Vote is checked and stored, and while voting closes, so a Vote
    # is either stored before the ballot box closes or refused (`vote_closed`).
    ballot_box: asyncio.Lock = field(default_factory=asyncio.Lock)


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
        self._sweeper: asyncio.Task | None = None

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    # --- Inactivity expiry -------------------------------------------------

    def start_expiry_sweeper(self) -> None:
        """Expire inactive Sessions in the background (call once the event loop runs)."""
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep_forever(), name="session-expiry")

    async def _sweep_forever(self) -> None:
        timeout = self._config.timings.inactivity_timeout_minutes * 60
        interval = min(max(timeout / 4, 1.0), 30.0)
        while True:
            await asyncio.sleep(interval)
            try:
                await self.expire_inactive()
            except Exception:  # noqa: BLE001 - e.g. DB briefly down; try again next tick
                log.exception("Expiry sweep failed")

    async def expire_inactive(self, room_code: str | None = None) -> list[str]:
        """Mark `waiting`/`active` Sessions with no activity for the configured
        timeout as `expired` (one Session, or all), and tell their sockets.

        A Session whose Rounds are running in this process never expires: its
        timers keep it moving. So `active` only expires when nothing runs it any
        more, e.g. it was left `active` by an app restart mid-Session.
        Called by the background sweeper and lazily before every lookup, so REST
        and joins see the expiry on time even between sweeps.
        """
        cutoff = _now() - timedelta(minutes=self._config.timings.inactivity_timeout_minutes)
        query = update(sessions).where(
            sessions.c.status.in_((WAITING, ACTIVE)), sessions.c.last_activity < cutoff
        )
        if room_code is not None:
            query = query.where(sessions.c.room_code == room_code)
        if self._runs:
            query = query.where(sessions.c.room_code.not_in(list(self._runs)))
        async with self._db.begin() as conn:
            expired = (
                await conn.execute(query.values(status=EXPIRED, expires_at=func.now()).returning(sessions.c.room_code))
            ).scalars().all()
        for code in expired:
            log.info("Session %s expired after inactivity", code)
            await self._emit(Event(code, {"type": "closed", "reason": "expired"}))
        return list(expired)

    async def _emit(self, event: Event) -> None:
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not break the Session
                log.exception("Event subscriber failed")

    async def shutdown(self) -> None:
        """Cancel every Session's timer task and the expiry sweeper (app shutdown)."""
        tasks = [run.task for run in self._runs.values() if run.task]
        if self._sweeper is not None:
            tasks.append(self._sweeper)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- Session creation and lookup -------------------------------------

    async def create_session(self) -> CreatedSession:
        """Create a `waiting` Session under the active Condition, with a fresh Researcher token."""
        room_code = secrets.token_urlsafe(9)  # 12 URL-safe chars, ~72 bits: not enumerable
        token = secrets.token_urlsafe(24)
        async with self._db.begin() as conn:
            await conn.execute(
                insert(sessions).values(
                    room_code=room_code,
                    condition=self._config.condition.name,
                    status=WAITING,
                    researcher_token_hash=_token_hash(token),
                )
            )
        log.info("Created Session %s (condition=%s)", room_code, self._config.condition.name)
        return CreatedSession(room_code=room_code, researcher_token=token)

    async def researcher_status(self, room_code: str, token: str | None) -> dict[str, Any]:
        """The Condition and Human slots filled/total, for the Researcher only.

        Never part of anything a Human receives: the slot count would give away
        how many Humans there are, i.e. the Condition (Blind Condition). Raises
        SessionNotFound, or WrongResearcherToken for a missing or wrong token.
        An expired Session is reported as such, not refused.
        """
        await self.expire_inactive(room_code)
        async with self._db.connect() as conn:
            session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
            if session is None:
                raise SessionNotFound(room_code)
            expected = session.researcher_token_hash
            if not token or expected is None or not hmac.compare_digest(_token_hash(token), expected):
                raise WrongResearcherToken(room_code)
            filled = (
                await conn.execute(
                    select(func.count())
                    .select_from(participants)
                    .where(participants.c.session_id == session.id, participants.c.type == HUMAN)
                )
            ).scalar_one()
        condition = Condition.named(session.condition)
        return {
            "room_code": room_code,
            "status": session.status,
            "condition": {
                "name": condition.name,
                "description": condition.describe(),
                "humans": condition.human_slots,
                "ai_agents": condition.ai_slots,
            },
            "filled": filled,
            "total": condition.human_slots,
        }

    async def public_state(self, room_code: str) -> dict[str, Any]:
        """Status, Round, Phase, deadline and Player Labels (Dropouts included). Never Participant types.
        Raises SessionNotFound or SessionExpired."""
        await self.expire_inactive(room_code)
        async with self._db.connect() as conn:
            session = await self._load_session(conn, room_code)
            # Dropouts stay listed: only Humans drop out, so hiding their label would
            # reveal a Human and signal presence (Blind Condition). Before the start a
            # Human who leaves is deleted, so the Waiting Room still shows who is there.
            labels = (
                await conn.execute(
                    select(participants.c.player_label)
                    .where(participants.c.session_id == session.id)
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
            "player_labels": [PlayerLabel.format(label) for label in labels],
        }

    async def ensure_exists(self, room_code: str) -> None:
        """Raises SessionNotFound, or SessionExpired for an expired Session."""
        await self.expire_inactive(room_code)
        async with self._db.connect() as conn:
            await self._load_session(conn, room_code)

    @staticmethod
    async def _load_session(conn, room_code: str):
        """The Session row for a Room Code. Raises SessionNotFound, or SessionExpired."""
        session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
        if session is None:
            raise SessionNotFound(room_code)
        if session.status == EXPIRED:
            raise SessionExpired(room_code)
        return session

    # --- Waiting Room ----------------------------------------------------

    async def join(self, room_code: str) -> JoinedParticipant:
        """Reserve a Human slot with a random unused Player Label, or raise JoinRefused."""
        await self.expire_inactive(room_code)
        async with self._locks.get(room_code):
            async with self._db.begin() as conn:
                session = (await conn.execute(select(sessions).where(sessions.c.room_code == room_code))).first()
                if session is None:
                    raise JoinRefused("not_found")
                if session.status != WAITING:
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
                        .values(session_id=session.id, player_label=label, type=HUMAN)
                        .returning(participants.c.id)
                    )
                ).scalar_one()
                await conn.execute(
                    update(sessions).where(sessions.c.id == session.id).values(last_activity=func.now())
                )
        log.info("Human joined Session %s as Player %s", room_code, label)
        return JoinedParticipant(id=participant_id, session_id=session.id, room_code=room_code, player_label=label)

    async def connected(self, participant: JoinedParticipant) -> None:
        """The joiner's socket is registered: tell them their label and that they
        are waiting, then start the Session if this filled the last Human slot."""
        await self._emit(
            Event(
                participant.room_code,
                {"type": "joined", "player_label": PlayerLabel.format(participant.player_label)},
                recipient=participant.id,
            )
        )
        run = self._runs.get(participant.room_code)
        if run is not None and run.phase is not None:
            # Reserved a slot before the start but connected just after it: catch up.
            await self._emit(Event(participant.room_code, self._phase_frame(run), recipient=participant.id))
            return
        # Only the joiner hears this, and without a slot count: a count, or a frame to
        # everyone on each join/leave, would let Humans count each other (Blind Condition).
        # The Researcher sees the count via `researcher_status`.
        await self._emit(Event(participant.room_code, {"type": "waiting"}, recipient=participant.id))
        try:
            await self.start(participant.room_code, only_when_full=True)
        except (NotWaiting, SessionNotFound):
            pass

    async def disconnected(self, participant: JoinedParticipant) -> None:
        """A Human's socket closed. Before the start this frees their slot; during
        an active Session it makes them a Dropout. Afterwards it changes nothing."""
        async with self._locks.get(participant.room_code):
            async with self._db.begin() as conn:
                status = (
                    await conn.execute(select(sessions.c.status).where(sessions.c.id == participant.session_id))
                ).scalar_one_or_none()
                if status == ACTIVE:
                    await self._drop_out(conn, participant)
                    return
                if status != WAITING:
                    return  # completed or expired: nothing left to take part in
                await conn.execute(delete(participants).where(participants.c.id == participant.id))
                await conn.execute(
                    update(sessions).where(sessions.c.id == participant.session_id).values(last_activity=func.now())
                )
        log.info("Player %s left Session %s before the start", participant.player_label, participant.room_code)

    async def _drop_out(self, conn, participant: JoinedParticipant) -> None:
        """Mark a Dropout: `dropped_out_at`, Session `incomplete`, and every Vote
        they can no longer cast written as `missing` (never an Abstention).

        They leave `run.present`, so `vote()` refuses them and the early end of
        voting only waits for those still connected. They cannot rejoin: joins
        are only accepted while the Session is waiting. Nobody is told (no
        presence signals, Blind Condition); the Session just carries on.
        """
        now = _now()
        await conn.execute(
            update(participants).where(participants.c.id == participant.id).values(dropped_out_at=now)
        )
        await conn.execute(
            update(sessions).where(sessions.c.id == participant.session_id).values(incomplete=True, last_activity=now)
        )
        run = self._runs.get(participant.room_code)
        if run is None:
            return
        run.present.discard(participant.id)
        # The current Round only if they have not voted in it yet (`run.voted` is
        # claimed before the Vote insert awaits, so this cannot race it), and not
        # once the ballot box has closed: the close gives them an Abstention.
        first = run.round or 1
        if run.phase == VOTING and (participant.id in run.voted or run.phase_over.is_set()):
            first += 1
        rows = [
            {
                "session_id": participant.session_id,
                "round_number": n,
                "participant_id": participant.id,
                "kind": MISSING,
                "cast_at": now,
            }
            for n in range(first, self._config.number_of_rounds + 1)
        ]
        if rows:
            await conn.execute(pg_insert(votes).values(rows).on_conflict_do_nothing())
        self._end_voting_if_all_voted(run)
        log.info("Player %s dropped out of Session %s (Incomplete Session)", participant.player_label, participant.room_code)

    # --- Start -----------------------------------------------------------

    async def start(self, room_code: str, *, only_when_full: bool = False) -> None:
        """waiting -> active: add AI Agents for the Condition's AI slots and run Round 1.

        The manual start endpoint calls this directly; `connected()` calls it with
        `only_when_full` so it fires once every Human slot is taken.
        Raises SessionNotFound, SessionExpired, or NotWaiting when the Session is not waiting.
        """
        await self.expire_inactive(room_code)
        async with self._locks.get(room_code):
            async with self._db.begin() as conn:
                session = await self._load_session(conn, room_code)
                if session.status != WAITING:
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
                        insert(participants).values(session_id=session.id, player_label=label, type=AI)
                    )
                await conn.execute(
                    update(sessions)
                    .where(sessions.c.id == session.id)
                    .values(status=ACTIVE, last_activity=func.now())
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
        # No await until both lines ran: from here `vote()` refuses and `_drop_out`
        # leaves this Round alone, so whoever was present at the close (even if they
        # disconnect a moment later) gets an Abstention rather than `missing`.
        run.phase_over.set()  # closes the ballot box
        present_at_close = set(run.present)
        ended = _now()
        async with run.ballot_box:  # wait for a Vote that is being stored right now
            voted = set(run.voted)
        # Whoever did not vote: an Abstention if still present, else missing (Dropout).
        # ON CONFLICT DO NOTHING keeps a row already written (e.g. by #16 at dropout).
        absent = [
            {
                "session_id": run.session_id,
                "round_number": round_number,
                "participant_id": pid,
                "kind": ABSTENTION if pid in present_at_close else MISSING,
                "cast_at": ended,
            }
            for pid in run.labels
            if pid not in voted
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
                    status=COMPLETED,
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
            "counts": {PlayerLabel.format(label): n for label, n in sorted(result.counts.items())},
            "decision_maker": PlayerLabel.format(result.decision_maker),
        }
        if types is not None:
            frame["types"] = {PlayerLabel.format(label): kind for label, kind in sorted(types.items())}
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
            "player_labels": [PlayerLabel.format(label) for label in sorted(run.labels.values())],  # the ballot
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
                    "player_label": PlayerLabel.format(participant.player_label),
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
        if run is None:
            await self._reject(participant, "vote_closed")
            return
        # Checked and stored under the ballot box lock: closing the Voting Phase
        # waits for a Vote in flight, so a stored Vote is always counted.
        async with run.ballot_box:
            reason = self._vote_refusal(run, participant, target)
            if reason is None:
                round_number = run.round
                await self._store_vote(run, participant, target)
                self._end_voting_if_all_voted(run)
        if reason is not None:
            await self._reject(participant, reason)
            return
        await self._emit(
            Event(participant.room_code, {"type": "vote_recorded", "round": round_number}, recipient=participant.id)
        )

    @staticmethod
    def _vote_refusal(run: _Run, participant: JoinedParticipant, target: Any) -> str | None:
        if run.phase != VOTING or run.phase_over.is_set() or participant.id not in run.present:
            return "vote_closed"
        if PlayerLabel.parse(target) not in run.labels.values():
            return "bad_vote"
        if participant.id in run.voted:
            return "already_voted"
        return None

    async def _store_vote(self, run: _Run, participant: JoinedParticipant, target: str) -> None:
        letter = PlayerLabel.parse(target)
        target_id = next(pid for pid, label in run.labels.items() if label == letter)
        run.voted.add(participant.id)  # before any await: `_drop_out` reads it without the lock
        cast_at = _now()
        try:
            async with self._db.begin() as conn:
                await conn.execute(
                    insert(votes).values(
                        session_id=participant.session_id,
                        round_number=run.round,
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
        except BaseException:
            run.voted.discard(participant.id)  # not stored: they get an Abstention instead
            raise

    @staticmethod
    def _end_voting_if_all_voted(run: _Run) -> None:
        """End the Voting Phase early once every present Participant has voted."""
        if run.phase == VOTING and run.present <= run.voted:
            run.phase_over.set()

    async def _reject(self, participant: JoinedParticipant, reason: str) -> None:
        await self._emit(Event(participant.room_code, {"type": "error", "reason": reason}, recipient=participant.id))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _human_slots(condition: str) -> int:
    """Human slots of the Condition the Session was created under (not today's config)."""
    return CONDITIONS[condition][0]
