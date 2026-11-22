"""LLM client interface for AI Agents, plus the mock used in mock mode.

The AI Agent runner only talks to `LLMClient`. It hands over an `AgentView`
(what that AI Agent can see: its own Player Label, the Round, the ballot and
the chat history) and gets back text:

- `write_message(view)` -> the next chat message (opening or reply).
- `choose_vote(view)` -> a raw answer naming a Player Label. The runner parses
  it and falls back to a random Vote if it can't.

Either method may raise; the runner then skips that message (or votes at
random). `MockLLMClient` needs no network and no env vars.
`OpenAICompatibleClient` fills the `prompts:` templates from config.yml and
calls any OpenAI-compatible `/chat/completions` endpoint set by the LLM_* env
vars. `make_llm_client` picks one based on `mock_mode`.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from .config import Config, LLMParameters, LLMSettings, Prompts

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
    """Mock in mock mode, otherwise the OpenAI-compatible client (env vars checked by the config loader)."""
    if config.mock_mode:
        return MockLLMClient()
    log.info("AI Agents use the LLM %s at %s", config.llm.model, config.llm.base_url)
    return OpenAICompatibleClient(config.llm, config.prompts, config.llm_parameters)


# --- OpenAI-compatible -------------------------------------------------------


class LLMError(Exception):
    """The LLM call failed or gave an unusable answer. The runner skips the message."""


# A message that gives the game away is dropped rather than sent (Blind Condition).
_REVEALS_AI = re.compile(
    r"\b(as an ai|an ai\b|i'?m an? (ai|bot|language model)|i am an? (ai|bot|language model)|language model|"
    r"chatbot|ai assistant|openai|chatgpt)",
    re.IGNORECASE,
)
_THINK = re.compile(r"<think>.*?(</think>|$)", re.IGNORECASE | re.DOTALL)
_OWN_PREFIX = re.compile(r"^\s*\**player\s*[a-z]\**\s*[:\-]\s*", re.IGNORECASE)
MAX_MESSAGE_CHARS = 300


class OpenAICompatibleClient:
    """Calls `POST {LLM_BASE_URL}/chat/completions` (OpenAI, Ollama, vLLM, LM Studio, ...).

    One system message (`prompts.system`) and one user message (the chat history
    plus `prompts.opening` / `reply` / `vote`). Any HTTP error, timeout or empty
    answer raises `LLMError`.
    """

    def __init__(self, llm: LLMSettings, prompts: Prompts, params: LLMParameters):
        self._url = llm.base_url.rstrip("/") + "/chat/completions"
        self._model = llm.model
        self._headers = {"Authorization": f"Bearer {llm.api_key}"} if llm.api_key else {}
        self._prompts = prompts
        self._params = params

    async def write_message(self, view: AgentView) -> str:
        template = self._prompts.opening if view.purpose == "opening" else self._prompts.reply
        text = await self._complete(view, template)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = _OWN_PREFIX.sub("", lines[0] if lines else "").strip().strip('"').strip()
        if not text:
            raise LLMError("empty message")
        if _REVEALS_AI.search(text):
            raise LLMError(f"message would reveal an AI Agent: {text!r}")
        return text[:MAX_MESSAGE_CHARS]

    async def choose_vote(self, view: AgentView) -> str:
        return await self._complete(view, self._prompts.vote)

    async def _complete(self, view: AgentView, template: str) -> str:
        values = _placeholders(view)
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._prompts.system.format(**values)},
                {"role": "user", "content": template.format(**values)},
            ],
            "temperature": self._params.temperature,
            "max_tokens": self._params.max_tokens,
        }
        if self._params.reasoning_effort:
            body["reasoning_effort"] = self._params.reasoning_effort
        try:
            async with httpx.AsyncClient(timeout=self._params.timeout_seconds) as http:
                response = await http.post(self._url, json=body, headers=self._headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"LLM call failed: {exc!r}") from exc
        content = _THINK.sub("", content or "").strip()
        if not content:
            raise LLMError("empty answer")
        return content


def _placeholders(view: AgentView) -> dict[str, str]:
    history = "\n".join(
        f"{line.player_label}{' (you)' if line.player_label == view.player_label else ''}: {line.text}"
        for line in view.history
    )
    return {
        "player_label": view.player_label,
        "other_labels": ", ".join(label for label in view.player_labels if label != view.player_label),
        "player_labels": ", ".join(view.player_labels),
        "round": str(view.round),
        "tone": view.tone,
        "history": history or "(no messages yet)",
    }


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
