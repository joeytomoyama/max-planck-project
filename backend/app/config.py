"""Config loader: reads and validates `config.yml` once at startup.

Everything else in the app gets its settings from the `Config` object returned
by `load_config()`. A bad file raises `ConfigError` with a message meant for the
Researcher; `app.__main__` prints it and exits before the server starts.

LLM endpoint, model and key never live in `config.yml`; they come from the
environment only (see `LLMSettings.from_env`), and none are needed to start.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

NUMBER_OF_ROUNDS = 2  # fixed by the spec, not configurable

# Condition value -> (Human slots, AI Agent slots). Every Session has 3 Participants.
CONDITIONS: dict[str, tuple[int, int]] = {
    "3_humans": (3, 0),
    "2_humans_1_ai": (2, 1),
    "1_human_2_ai": (1, 2),
}


class ConfigError(Exception):
    """`config.yml` is missing or invalid. The message is shown to the Researcher."""


@dataclass(frozen=True)
class Condition:
    name: str
    human_slots: int
    ai_slots: int


@dataclass(frozen=True)
class Timings:
    discussion_seconds: float
    voting_seconds: float
    inactivity_timeout_minutes: float


@dataclass(frozen=True)
class AIAgentSettings:
    """How AI Agents chat and vote (`ai_agents:` in config.yml). Prompts: `Prompts`."""

    reply_rate: float  # chance of replying to each message from another Participant
    message_delay_seconds: tuple[float, float]  # (min, max) wait before each message
    max_messages_per_phase: int  # cap per Discussion Phase, opening message included
    vote_delay_seconds: tuple[float, float]  # (min, max) wait before voting
    tone: str  # chat style, e.g. "casual"


# Placeholders AI Agent prompt templates may use (filled by the real LLM client).
PROMPT_PLACEHOLDERS = ("player_label", "other_labels", "player_labels", "round", "tone", "history")


@dataclass(frozen=True)
class Prompts:
    """AI Agent prompt templates (`prompts:` in config.yml), used only with mock mode off."""

    system: str  # who the AI Agent is and how it writes
    opening: str  # first message of a Discussion Phase
    reply: str  # reply to the latest messages
    vote: str  # pick one Player Label


@dataclass(frozen=True)
class LLMParameters:
    """Request parameters for the LLM (`llm_parameters:` in config.yml). Never the key or URL."""

    temperature: float
    max_tokens: int
    timeout_seconds: float
    reasoning_effort: str | None  # e.g. "none" to turn off thinking in reasoning models; None = not sent


@dataclass(frozen=True)
class LLMSettings:
    """OpenAI-compatible endpoint settings. All optional; only needed with mock mode off."""

    base_url: str | None
    model: str | None
    api_key: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "LLMSettings":
        return cls(
            base_url=env.get("LLM_BASE_URL") or None,
            model=env.get("LLM_MODEL") or None,
            api_key=env.get("LLM_API_KEY") or None,
        )


@dataclass(frozen=True)
class Config:
    condition: Condition
    timings: Timings
    number_of_rounds: int
    mock_mode: bool
    mock_seed: int | None  # mock mode only: seeds mock answers and AI Agent timing; None = random
    reveal_identities_at_end: bool
    ai_agents: AIAgentSettings
    prompts: Prompts | None  # None only in mock mode without a `prompts:` section
    llm_parameters: LLMParameters
    llm: LLMSettings
    raw: Mapping[str, Any]  # the parsed file, for sections later modules own (e.g. AI Agent settings)

    def public_settings(self) -> dict[str, Any]:
        """Settings safe to send to browsers. Never the Condition (Blind Condition)."""
        return {
            "discussion_seconds": self.timings.discussion_seconds,
            "voting_seconds": self.timings.voting_seconds,
            "number_of_rounds": self.number_of_rounds,
        }


def default_config_path() -> Path:
    return Path(os.environ.get("CONFIG_PATH", "config.yml"))


def load_config(path: Path | None = None, env: Mapping[str, str] = os.environ) -> Config:
    path = path or default_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping of keys to values")

    condition = _condition(data)  # first: a bad Condition is always the error reported
    mock_mode = _bool(data, "mock_mode", default=True)
    llm = LLMSettings.from_env(env)
    prompts = _prompts(data.get("prompts"), required=not mock_mode)
    if not mock_mode and not (llm.base_url and llm.model):
        raise ConfigError(
            "`mock_mode: false` needs an LLM: set the environment variables LLM_BASE_URL and LLM_MODEL "
            "(and LLM_API_KEY if the endpoint needs one), or set `mock_mode: true` in config.yml"
        )
    return Config(
        condition=condition,
        timings=_timings(data.get("timings") or {}),
        number_of_rounds=NUMBER_OF_ROUNDS,
        mock_mode=mock_mode,
        mock_seed=_mock_seed(data),
        reveal_identities_at_end=_bool(data, "reveal_identities_at_end", default=False),
        ai_agents=_ai_agents(data.get("ai_agents") or {}),
        prompts=prompts,
        llm_parameters=_llm_parameters(data.get("llm_parameters") or {}),
        llm=llm,
        raw=data,
    )


def _prompts(section: Any, required: bool) -> Prompts | None:
    if section is None and not required:
        return None
    if not isinstance(section, dict):
        raise ConfigError("`prompts:` in config.yml must be a mapping with system, opening, reply and vote")
    values = {}
    dummy = {name: "x" for name in PROMPT_PLACEHOLDERS}
    for key in ("system", "opening", "reply", "vote"):
        value = section.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Missing or empty `prompts.{key}` in config.yml")
        try:
            value.format(**dummy)
        except (KeyError, IndexError, ValueError) as exc:
            allowed = ", ".join("{" + name + "}" for name in PROMPT_PLACEHOLDERS)
            raise ConfigError(f"Bad placeholder {exc} in `prompts.{key}` in config.yml. Allowed: {allowed}") from None
        values[key] = value.strip()
    return Prompts(**values)


def _llm_parameters(section: Any) -> LLMParameters:
    if not isinstance(section, dict):
        raise ConfigError("`llm_parameters:` in config.yml must be a mapping")

    def positive(key: str, default: float) -> float:
        value = section.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigError(f"Invalid `llm_parameters.{key}: {value}` in config.yml. Must be a positive number")
        return value

    temperature = section.get("temperature", 0.9)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
        raise ConfigError(f"Invalid `llm_parameters.temperature: {temperature}` in config.yml. Must be between 0 and 2")
    max_tokens = positive("max_tokens", 80)
    if int(max_tokens) != max_tokens:
        raise ConfigError(f"Invalid `llm_parameters.max_tokens: {max_tokens}` in config.yml. Must be a whole number")
    effort = section.get("reasoning_effort")
    if effort is not None and (not isinstance(effort, str) or not effort.strip()):
        raise ConfigError(f"Invalid `llm_parameters.reasoning_effort: {effort}` in config.yml. Must be text or left out")
    return LLMParameters(
        temperature=temperature,
        max_tokens=int(max_tokens),
        timeout_seconds=positive("timeout_seconds", 20),
        reasoning_effort=effort.strip() if effort else None,
    )


def _condition(data: Mapping[str, Any]) -> Condition:
    valid = " | ".join(CONDITIONS)
    if "condition" not in data or data["condition"] is None:
        raise ConfigError(f"Missing `condition:` in config.yml. Valid options: {valid}")
    value = data["condition"]
    if not isinstance(value, str) or value not in CONDITIONS:
        raise ConfigError(f"Invalid `condition: {value}` in config.yml. Valid options: {valid}")
    humans, ais = CONDITIONS[value]
    return Condition(name=value, human_slots=humans, ai_slots=ais)


def _timings(section: Any) -> Timings:
    if not isinstance(section, dict):
        raise ConfigError("`timings:` in config.yml must be a mapping")
    defaults = {"discussion_seconds": 60, "voting_seconds": 20, "inactivity_timeout_minutes": 15}
    values = {}
    for key, default in defaults.items():
        value = section.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigError(f"Invalid `timings.{key}: {value}` in config.yml. Must be a positive number")
        values[key] = value
    return Timings(**values)


def _ai_agents(section: Any) -> AIAgentSettings:
    if not isinstance(section, dict):
        raise ConfigError("`ai_agents:` in config.yml must be a mapping")

    def number(key: str, default: float, low: float, high: float | None = None) -> float:
        value = section.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < low or (high is not None and value > high):
            bounds = f"between {low} and {high}" if high is not None else f"at least {low}"
            raise ConfigError(f"Invalid `ai_agents.{key}: {value}` in config.yml. Must be a number {bounds}")
        return value

    def span(key: str, default: tuple[float, float]) -> tuple[float, float]:
        value = section.get(key, {"min": default[0], "max": default[1]})
        low, high = (value.get("min"), value.get("max")) if isinstance(value, dict) else (None, None)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in (low, high)) or low > high:
            raise ConfigError(
                f"Invalid `ai_agents.{key}: {value}` in config.yml. Must be {{min: N, max: M}} with 0 <= N <= M"
            )
        return (low, high)

    max_messages = number("max_messages_per_phase", 4, 0)
    if int(max_messages) != max_messages:
        raise ConfigError(f"Invalid `ai_agents.max_messages_per_phase: {max_messages}` in config.yml. Must be a whole number")
    tone = section.get("tone", "casual")
    if not isinstance(tone, str) or not tone.strip():
        raise ConfigError(f"Invalid `ai_agents.tone: {tone}` in config.yml. Must be text")
    return AIAgentSettings(
        reply_rate=number("reply_rate", 0.5, 0, 1),
        message_delay_seconds=span("message_delay_seconds", (3, 10)),
        max_messages_per_phase=int(max_messages),
        vote_delay_seconds=span("vote_delay_seconds", (1, 4)),
        tone=tone.strip(),
    )


def _mock_seed(data: Mapping[str, Any]) -> int | None:
    value = data.get("mock_seed")
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ConfigError(f"Invalid `mock_seed: {value}` in config.yml. Must be a whole number or left out")
    return value


def _bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"Invalid `{key}: {value}` in config.yml. Must be true or false")
    return value
