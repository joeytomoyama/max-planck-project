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
    """How AI Agents chat and vote (`ai_agents:` in config.yml). Prompts: #15."""

    reply_rate: float  # chance of replying to each message from another Participant
    message_delay_seconds: tuple[float, float]  # (min, max) wait before each message
    max_messages_per_phase: int  # cap per Discussion Phase, opening message included
    vote_delay_seconds: tuple[float, float]  # (min, max) wait before voting
    tone: str  # chat style, e.g. "casual"


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
    reveal_identities_at_end: bool
    ai_agents: AIAgentSettings
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

    return Config(
        condition=_condition(data),
        timings=_timings(data.get("timings") or {}),
        number_of_rounds=NUMBER_OF_ROUNDS,
        mock_mode=_bool(data, "mock_mode", default=True),
        reveal_identities_at_end=_bool(data, "reveal_identities_at_end", default=False),
        ai_agents=_ai_agents(data.get("ai_agents") or {}),
        llm=LLMSettings.from_env(env),
        raw=data,
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


def _bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"Invalid `{key}: {value}` in config.yml. Must be true or false")
    return value
