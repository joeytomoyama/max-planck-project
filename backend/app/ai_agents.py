"""AI Agent runner: makes AI Agents chat and vote like Humans.

`AIAgents` subscribes to the Session engine's events, exactly like the
realtime hub does. When a Session's first `phase` frame goes out, it loads that
Session's AI Agents from the database and creates one `AIAgentRunner` each.
Runners only see the frames a browser would see (Player Labels, never types),
and they act through the same engine methods the hub uses for Humans
(`engine.chat`, `engine.vote`), so their messages and Votes are identical on
the wire.

Per Discussion Phase a runner posts an opening message, replies to each
message from another Participant with probability `reply_rate`, waits a random
`message_delay_seconds` before each message, and sends at most
`max_messages_per_phase`. In each Voting Phase it votes once after
`vote_delay_seconds` (capped to fit the Phase). Text and Votes come from an
`LLMClient`; answers are cached per (AI Agent, what it sees). A failing LLM call
skips the message; an unusable vote answer becomes a random Vote.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import AIAgentSettings
from .llm import AgentView, ChatLine, LLMClient
from .persistence import participants, sessions
from .session_engine import DISCUSSION, VOTING, Event, JoinedParticipant, SessionEngine

log = logging.getLogger(__name__)


class AIAgentRunner:
    """One AI Agent in one Session. Fed wire frames via `on_frame`."""

    def __init__(
        self,
        engine: SessionEngine,
        me: JoinedParticipant,
        settings: AIAgentSettings,
        client: LLMClient,
        rng: random.Random | None = None,
    ):
        self._engine = engine
        self._me = me
        self._label = f"Player {me.player_label}"
        self._settings = settings
        self._client = client
        self._rng = rng or random.Random()
        self._round: int | None = None
        self._phase: str | None = None
        self._deadline: datetime | None = None
        self._ballot: tuple[str, ...] = ()
        self._history: list[ChatLine] = []
        self._used = 0  # messages sent or scheduled in this Discussion Phase
        self._tasks: set[asyncio.Task] = set()
        self._cache: dict[AgentView, str] = {}

    def on_frame(self, frame: dict[str, Any]) -> None:
        kind = frame.get("type")
        if kind == "phase":
            self._new_phase(frame)
        elif kind == "chat":
            self._history.append(ChatLine(frame["player_label"], frame["text"]))
            if frame["player_label"] != self._label and self._phase == DISCUSSION:
                if self._rng.random() < self._settings.reply_rate:
                    self._schedule_message("reply")

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    # --- Phases ----------------------------------------------------------

    def _new_phase(self, frame: dict[str, Any]) -> None:
        self.stop()  # anything still pending belongs to the previous Phase
        self._round, self._phase = frame["round"], frame["phase"]
        self._deadline = datetime.fromisoformat(frame["deadline"])
        self._ballot = tuple(frame.get("player_labels") or ())
        if self._phase == DISCUSSION:
            self._used = 0
            self._schedule_message("opening")
        elif self._phase == VOTING:
            self._spawn(self._vote())

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro, name=f"ai-{self._me.room_code}-{self._me.player_label}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _view(self, purpose: str) -> AgentView:
        return AgentView(
            player_label=self._label,
            round=self._round,
            player_labels=self._ballot,
            history=tuple(self._history),
            purpose=purpose,
            tone=self._settings.tone,
        )

    # --- Chat ------------------------------------------------------------

    def _schedule_message(self, purpose: str) -> None:
        if self._used >= self._settings.max_messages_per_phase:
            return
        self._used += 1
        self._spawn(self._send_message(purpose))

    async def _send_message(self, purpose: str) -> None:
        await asyncio.sleep(self._rng.uniform(*self._settings.message_delay_seconds))
        view = self._view(purpose)  # the chat as it stands when the AI Agent "types"
        try:
            text = self._cache.get(view)
            if text is None:
                text = await self._client.write_message(view)
                self._cache[view] = text
        except Exception:  # noqa: BLE001 - an LLM error skips this message, never the Session
            log.warning("AI Agent %s in %s: LLM call failed, message skipped", self._label, self._me.room_code, exc_info=True)
            return
        await self._engine.chat(self._me, text)

    # --- Voting ----------------------------------------------------------

    async def _vote(self) -> None:
        low, high = self._settings.vote_delay_seconds
        remaining = (self._deadline - datetime.now(timezone.utc)).total_seconds()
        await asyncio.sleep(max(0.0, min(self._rng.uniform(low, high), remaining - 1.0)))
        view = self._view("vote")
        try:
            answer = self._cache.get(view)
            if answer is None:
                answer = await self._client.choose_vote(view)
                self._cache[view] = answer
            target = self._parse_vote(answer)
        except Exception:  # noqa: BLE001 - fall back to a random Vote
            log.warning("AI Agent %s in %s: LLM vote failed", self._label, self._me.room_code, exc_info=True)
            target = None
        if target is None:
            target = self._rng.choice(self._ballot)
            log.info("AI Agent %s in %s votes at random", self._label, self._me.room_code)
        await self._engine.vote(self._me, target)

    def _parse_vote(self, answer: str) -> str | None:
        """First Player Label named in the answer ("Player B", "player b", or a bare "B")."""
        letters = {label.removeprefix("Player "): label for label in self._ballot}
        match = re.search(r"\bplayer\s*([a-z])\b", answer, re.IGNORECASE) or re.fullmatch(
            r"\W*([a-z])\W*", answer, re.IGNORECASE
        )
        return letters.get(match.group(1).upper()) if match else None


class AIAgents:
    """Creates and feeds the runners of every active Session's AI Agents."""

    def __init__(self, engine: SessionEngine, db: AsyncEngine, settings: AIAgentSettings, client: LLMClient):
        self._engine = engine
        self._db = db
        self._settings = settings
        self._client = client
        self._rooms: dict[str, list[AIAgentRunner]] = {}  # room_code -> runners
        engine.subscribe(self._on_event)

    async def _on_event(self, event: Event) -> None:
        if event.recipient is not None:
            return  # personal frames (joined, vote_recorded, errors): nothing to react to
        kind = event.payload.get("type")
        if kind == "phase" and event.room_code not in self._rooms:
            self._rooms[event.room_code] = await self._load(event.room_code)
        if kind in ("result", "closed"):  # the Session is over
            for runner in self._rooms.pop(event.room_code, []):
                runner.stop()
            return
        for runner in self._rooms.get(event.room_code, []):
            runner.on_frame(event.payload)

    async def _load(self, room_code: str) -> list[AIAgentRunner]:
        async with self._db.connect() as conn:
            rows = (
                await conn.execute(
                    select(participants.c.id, participants.c.session_id, participants.c.player_label)
                    .join(sessions, sessions.c.id == participants.c.session_id)
                    .where(sessions.c.room_code == room_code, participants.c.type == "ai")
                )
            ).all()
        if rows:
            log.info("Session %s: %d AI Agent(s) take part", room_code, len(rows))
        return [
            AIAgentRunner(
                self._engine,
                JoinedParticipant(id=row.id, session_id=row.session_id, room_code=room_code, player_label=row.player_label),
                self._settings,
                self._client,
            )
            for row in rows
        ]

    def shutdown(self) -> None:
        for runners in self._rooms.values():
            for runner in runners:
                runner.stop()
        self._rooms.clear()
