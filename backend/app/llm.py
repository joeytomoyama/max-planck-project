"""LLM client interface for AI Agents, plus the mock used in mock mode.

The AI Agent runner only talks to `LLMClient`. It hands over an `AgentView`
(what that AI Agent can see: its own Player Label, the Round, the ballot and
the chat history) and gets back text:

- `write_message(view)` -> the next chat message (opening or reply).
- `choose_vote(view)` -> a raw answer naming a Player Label. The runner parses
  it and falls back to a random Vote if it can't.

Either method may raise; the runner then skips that message (or votes at
random). `MockLLMClient` needs no network and no env vars. The real
OpenAI-compatible client (ticket #15) implements the same two methods and is
picked in `make_llm_client`.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Literal, Protocol

from .config import Config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatLine:
    player_label: str  # "Player A"
    text: str


@dataclass(frozen=True)
class AgentView:
    """Everything an AI Agent knows when it acts. Hashable: it is the cache key."""

    player_label: str  # the AI Agent's own label, "Player B"
    round: int
    player_labels: tuple[str, ...]  # the ballot: every Player Label in the Session
    history: tuple[ChatLine, ...]  # all chat messages of the Session so far, oldest first
    purpose: Literal["opening", "reply", "vote"]
    tone: str = "casual"


class LLMClient(Protocol):
    async def write_message(self, view: AgentView) -> str: ...

    async def choose_vote(self, view: AgentView) -> str: ...


def make_llm_client(config: Config) -> LLMClient:
    """Mock in mock mode. The real OpenAI-compatible client arrives with #15."""
    if not config.mock_mode:
        log.warning("mock_mode is off but no real LLM client exists yet; AI Agents use the mock")
    return MockLLMClient()


# --- Mock ------------------------------------------------------------------

_OPENINGS = (
    "hey all",
    "hi everyone",
    "ok so who wants to be decision maker",
    "hey, so how do we pick",
    "hi! no strong opinion yet tbh",
    "hello, i think we should just pick whoever seems most level headed",
    "hey hey. anyone want to volunteer?",
)
_REPLIES = (
    "yeah fair point",
    "hmm not sure about that",
    "i could go either way honestly",
    "agree with {other}",
    "{other} makes sense to me",
    "what do you think {other}?",
    "i'd be fine doing it if nobody else wants to",
    "lol ok",
    "true, but who's actually good at deciding stuff",
    "idk, maybe {other}?",
    "sounds reasonable",
    "i'm leaning towards {other} tbh",
)
_TAILS = ("", "", "", " lol", " tbh", "!", "...", " haha")


class MockLLMClient:
    """Scripted, slightly varied casual messages and random Votes. No network."""

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()

    async def write_message(self, view: AgentView) -> str:
        if view.purpose == "opening" and view.round == 1:
            base = self._rng.choice(_OPENINGS)
        elif view.purpose == "opening":
            base = self._rng.choice(("ok round 2", "so what are we thinking now", "still undecided here", "round 2, anyone changed their mind?"))
        else:
            base = self._rng.choice(_REPLIES)
        others = [label for label in view.player_labels if label != view.player_label]
        last_other = next((line.player_label for line in reversed(view.history) if line.player_label != view.player_label), None)
        other = last_other or (self._rng.choice(others) if others else "everyone")
        text = base.format(other=other.lower() if self._rng.random() < 0.5 else other)
        text += self._rng.choice(_TAILS)
        if self._rng.random() < 0.3:
            text = text[0].upper() + text[1:]
        return text

    async def choose_vote(self, view: AgentView) -> str:
        return self._rng.choice(view.player_labels)
