# AI Agent prompts

How AI Agents talk to the LLM when `mock_mode: false`. The prompts below are
the defaults in `config.yml` (`prompts:` and `llm_parameters:`); edit them there,
then restart the app. The development prompts (how this codebase was built with
AI tools) are in the AI Usage Log, `.github/AI-USAGE-LOG.md`.

## Endpoint and model

Any OpenAI-compatible `POST {LLM_BASE_URL}/chat/completions` endpoint. Set by
environment variables only, never in `config.yml`:

| Variable       | Example (local Ollama)                    | Required with mock mode off |
|----------------|-------------------------------------------|-----------------------------|
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1`    | yes                         |
| `LLM_MODEL`    | `qwen3.5:9b`                              | yes                         |
| `LLM_API_KEY`  | (empty for Ollama; your key for a hosted API) | no                      |

The app refuses to start with `mock_mode: false` if `LLM_BASE_URL` or `LLM_MODEL`
is missing. Mock mode needs none of them.

Model used for manual verification: **`qwen3.5:9b`** on a local Ollama, with the
parameters below and `reasoning_effort: none`.

## Parameters (`llm_parameters:` in config.yml)

| Parameter          | Default | Notes |
|--------------------|---------|-------|
| `temperature`      | 0.9     | Varied, human-sounding messages. |
| `max_tokens`       | 80      | Messages are one short line. |
| `timeout_seconds`  | 20      | A slower call counts as failed: the message is skipped. |
| `reasoning_effort` | not sent | Set to `none` for thinking models on Ollama (e.g. qwen3) so they answer directly instead of spending the token budget on reasoning. Leave it out for models that reject it. |

No other parameters are sent (no seed, no top_p, no streaming).

## Request shape

Every call sends two messages: the system prompt and one user prompt (opening,
reply or vote). Placeholders are filled from what that AI Agent can see, which is
exactly what a Human sees in the browser:

- `{player_label}`: the AI Agent's own Player Label, e.g. `Player B`
- `{other_labels}`: the other two Player Labels
- `{player_labels}`: all three (the ballot)
- `{round}`: 1 or 2
- `{tone}`: `ai_agents.tone` (default `casual`)
- `{history}`: every chat message of the Session so far, oldest first, one
  `Player X: text` per line; the AI Agent's own lines are marked `(you)`

## Prompts

### System

```
You are {player_label}, one of three people in an online group chat for a study.
The others are {other_labels}. Everyone only sees each other as "Player A/B/C".
The group has two short rounds of chat to agree who should be the Decision Maker,
then everyone votes for one player (voting for yourself is allowed).
Write like a real person typing quickly in a {tone} tone: one short message,
usually under 20 words, lowercase is fine, no emojis, no hashtags, no lists.
Never say or hint that you are an AI, a bot, a language model or an assistant.
If someone asks, act like a normal participant. Never put your own label in front
of your message; write only the message text.
```

### Opening (first message of each Discussion Phase)

```
Round {round} of 2 just started. Chat so far:
{history}

Write your first message for this round.
```

### Reply (to messages from other Participants)

```
Round {round} of 2. Chat so far:
{history}

Write your next message, reacting to what the others just said.
```

### Vote (once per Voting Phase)

```
The chat is over. Full chat:
{history}

Vote for who should be the Decision Maker: one of {player_labels}.
Answer with the Player Label only, e.g. "Player A".
```

## What happens to the answer

- **Chat:** any `<think>...</think>` block is removed, then the first non-empty
  line is kept, a leading `Player X:` and surrounding quotes are stripped, and it
  is cut to 300 characters. The message then goes through the same path and
  sanitizing as a Human's message, so it looks identical on the wire.
- **Blind Condition guard:** a message that mentions being an AI, a bot, a
  language model, an assistant, ChatGPT or OpenAI is dropped (not sent).
- **Vote:** the first `Player X` (or a bare letter) in the answer is the Vote.
  An answer with no usable Player Label becomes a random Vote.
- **Failures:** an HTTP error, timeout, malformed or empty answer skips that
  message; for a Vote it falls back to a random Vote. The Session never stalls.
- **Cache:** answers are cached per AI Agent and conversation state (Round,
  purpose, ballot and the full chat history) for the life of the Session, so the
  same state never triggers a second, different answer.
- **When AI Agents speak** (reply rate, delays, message cap) is set in
  `ai_agents:` in config.yml and does not depend on the LLM.

## Mock mode

With `mock_mode: true` no prompts are used. AI Agents pick scripted, slightly
varied casual lines (`_OPENINGS`, `_REPLIES`, `_TAILS` in `backend/app/llm.py`)
and vote at random.
