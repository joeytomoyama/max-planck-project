# Architecture

How the platform is built and why. Requirements: [SPEC.md](SPEC.md) (wins every
conflict) and spec issue #9. Terms follow [GLOSSARY.md](GLOSSARY.md).

## Overview

```
browser (React SPA)  ──REST /api/sessions...──▶ ┌──────────── app container ────────────┐
        ▲  │                                     │ FastAPI                               │
        │  └──WebSocket /ws/{room_code}────────▶ │  api.py ─┐                            │
        └──────── JSON frames ────────────────── │  realtime.py (hub) ─┐                 │
                                                 │                    ▼                  │
                                                 │  session_engine.py ◀── ai_agents.py   │
                                                 │       │   │              │            │
                                                 │ vote_tally.py      llm.py (mock|HTTP) │
                                                 └───────┼──────────────────┼────────────┘
                                                         ▼                  ▼
                                              db container (PostgreSQL)   OpenAI-compatible LLM
```

### One app image

SPEC.md asks for "two separate containers" but also for the React build to be
"copied into backend image" and served by FastAPI's StaticFiles (repeated in its
trade-offs). We followed the majority. The `Dockerfile` is multi-stage: Node
builds the React app, then a Python image runs FastAPI and serves the build.
`docker-compose.yml` adds a PostgreSQL container with a persistent `pgdata`
volume. There is no reverse proxy and no separate frontend container. Any path
that is not `/api/*`, `/ws/*` or a built file returns `index.html`, so the client
routes `/waiting` and `/room/:roomCode` survive a refresh.

- **Pro:** one image, one origin (no CORS), one command, fewer moving parts.
- **Con:** frontend and backend cannot be scaled or deployed separately, and a
  frontend change needs an image rebuild (`docker compose up --build`).

FastAPI's native WebSocket support is used. SPEC.md's "libwebsocket" (a C library)
is dropped.

`config.yml` is bind-mounted read-only into the container, so changing the
Condition or timings needs only `docker compose restart app`. It is read and
validated once at startup by `config.py`. An invalid value stops the process
with `CONFIG ERROR: ...` before the server starts, so no Session can run under a
Condition the Researcher did not intend. LLM endpoint, model and key come only
from environment variables, so keys never end up in the committed file.

## Modules

| Module | Job |
|---|---|
| `backend/app/config.py` | Loads and validates `config.yml` into a frozen `Config`. |
| `backend/app/session_engine.py` | Session lifecycle, every timer, chat, votes, Dropouts, expiry. Emits `Event`s; knows nothing about sockets. |
| `backend/app/vote_tally.py` | Pure function: all Rounds' ballots to the Result. |
| `backend/app/realtime.py` | The one WebSocket endpoint. Routes client frames to the engine and engine events to sockets. |
| `backend/app/api.py` | Thin REST layer over the engine. |
| `backend/app/ai_agents.py` | One runner per AI Agent per Session. Chats and votes through the engine like a Human. |
| `backend/app/llm.py` | `LLMClient` with two implementations: mock and OpenAI-compatible HTTP. |
| `backend/app/persistence.py` | SQLAlchemy Core tables; schema created on startup (no migrations, no seed script). |
| `frontend/src/room/useRoomSocket.js` | One socket per room page; folds server frames into UI state. The UI never polls. |

The engine is the only place game rules live. The hub and the AI Agent runner
both subscribe to its events, and both act through the same engine methods
(`chat`, `vote`). That shared path is what makes AI Agents indistinguishable on
the wire.

## Session flow

1. **Create.** `POST /api/sessions` (the Create Session button on `/waiting`)
   stores a `waiting` Session under the active Condition and returns a Room Code
   (`secrets.token_urlsafe(9)`: 12 URL-safe characters, ~72 bits, not enumerable)
   and the share link `/room/{room_code}`.
2. **Join.** A browser on the share link opens `/ws/{room_code}` and sends
   `{"type":"join"}`. The engine reserves a Human slot with a random unused Player
   Label (A/B/C) and broadcasts `waiting {filled, total}`. A join is refused with
   an `error` frame and a 44xx close code when the Session is not found, full,
   already active, completed or expired; the page shows a matching message.
3. **Start.** When the last Human slot fills, the engine runs the same
   `waiting → active` transition as `POST /api/sessions/{rc}/start`: AI Agents are
   inserted for the Condition's AI slots, using the remaining letters in random order.
   In `1_human_2_ai` the one Human starts the Session just by arriving.
4. **Rounds.** One asyncio task per Session walks exactly two Rounds: Discussion
   Phase (default 60 s) then Voting Phase (up to 20 s). Each Phase change sends a
   `phase` frame with the Round, the Phase, the server `deadline` and `server_time`.
5. **Result.** After Round 2's Voting Phase the engine tallies both Rounds, stores
   the Decision Maker, marks the Session `completed` and sends `result`.

### Server-owned timers

Every deadline is set and enforced on the server. Clients only render a countdown
from the `deadline` in the `phase` frame, corrected by the offset between
`server_time` and their own clock, so a wrong client clock changes neither the
display nor the outcome. Chat is accepted only during a Discussion Phase and Votes
only during an open Voting Phase. The trade-off: live Session state (current
Phase, deadline, who has voted) is kept in memory in one process, see
[Known limitations](#known-limitations).

### Chat

Plain text only. The server replaces line breaks with spaces, strips control and
invisible formatting characters (zero-width, bidi), trims, cuts to 500 characters
and rejects empty messages. React renders text, never HTML or Markdown. Each
message is stored with its Round, Phase and timestamp and broadcast as
`chat {player_label, text, sent_at}`.

## How the Blind Condition is enforced

The rule: nothing the server sends to a browser during a Session reveals whether a
Participant is a Human or an AI Agent.

- **Labels only.** Every frame and REST response identifies Participants only by
  Player Label. The engine's `JoinedParticipant` handle, used to route frames, has
  no type field. The type is stored in `participants.type` for the Researcher and
  read in exactly one place that reaches the wire: the Result, and only when
  `reveal_identities_at_end: true`.
- **No config leak.** `GET /api/sessions/{rc}/config` returns only the Phase
  timings and the number of Rounds, never the Condition (which would tell a Human
  how many AI Agents there are). The `waiting` frame shows the Human slot count
  (`1 of 2 joined`); that is needed for the Waiting Room and is not tied to any
  Player Label.
- **Random labels.** Humans get a random free letter on joining and AI Agents get
  the remaining letters in random order, so neither the letter nor join order
  gives anything away.
- **Same path, same format.** AI Agents call `engine.chat` / `engine.vote` with
  the same handle type as Humans, so their frames are byte-for-byte the same shape.
  Their messages pass the same sanitizer.
- **Human-like timing and text.** AI Agents wait 3–10 s before each message,
  reply to about half of the other messages, send at most about 4 per Discussion
  Phase, and write short casual lines. Real-LLM replies that admit being an AI,
  bot, language model or assistant are dropped. See [ai_prompts.md](ai_prompts.md).
- **No presence signals.** No typing indicators, no "Player X left" notice.
  A Dropout is invisible to the others.
- **Blind voting.** After a Vote the voter alone gets `vote_recorded`; nobody sees
  counts or choices before the Result.

Verified with Playwright MCP by capturing all WebSocket frames and REST bodies
during whole Sessions: no `human`/`ai`/`types` before the Result, and none in the
Result with the reveal off.

## Vote counting (ADR 0001)

[ADR 0001](docs/adr/0001-voting-design-for-human-vs-ai-choice.md) settles what
SPEC.md leaves open, for the research question "do people pick a Human or an AI
Agent as Decision Maker?":

- **Self-votes are allowed** ("for one of the three members").
- **Round 1 results stay hidden.** Showing them would mix herding into Round 2.
  Each Round is an independent measure, so a shift in preference can be studied.
- **Both Rounds count.** The Decision Maker has the most Votes across both Rounds
  (up to 6). A tie, including nobody voting, is broken by a random pick among the
  tied Player Labels, and `sessions.decided_by_tiebreak` records that, so a
  Researcher can tell a clear winner from an arbitrary one.

`vote_tally.tally` is a pure function (the random choice is injectable), so the
rule lives in one small place. Each Participant gets exactly one ballot row per
Round (`votes` is unique per Session, Round and Participant) with a `kind`:

| `kind` | Meaning | Counts for |
|---|---|---|
| `vote` | Voted for `target_participant` | that Participant |
| `abstention` | Present, but did not vote before the Voting Phase ended | nobody |
| `missing` | A Dropout: could not vote | nobody |

The Voting Phase ends early once every Participant still taking part (connected
Humans plus AI Agents) has voted. Each Round's counts, abstentions and missing
Votes are also stored in `rounds.vote_results` (JSONB).

## Dropouts

A Human whose socket closes after the Session started (closing the tab, losing the
connection, or refreshing) becomes a **Dropout**:

- `participants.dropped_out_at` is set and the Session is flagged
  `incomplete = true` (an Incomplete Session), so the Researcher can exclude it.
- Their Votes for every remaining Round are written as `missing` right away
  (including the current Round, unless they had already voted in it). Missing
  Votes are never Abstentions, so "didn't vote in time" stays a real data point.
- The Session continues for everyone else, unannounced. The early end of voting
  only waits for those still connected, so a Dropout never stalls the others.
- **No rejoining.** The server accepts joins only while a Session is `waiting`.
  In the browser that took part, the page remembers this
  (`localStorage` key `mpp.took-part.<roomCode>`) and shows "You can't rejoin this
  Session"; anywhere else the same refusal reads "This Session has already started".

Before the start, a disconnect is not a Dropout: it frees the slot (the row is deleted).

## Inactivity expiry

A `waiting` or `active` Session with no activity (joins, leaves, messages, Votes,
start) for `timings.inactivity_timeout_minutes` (default 15) becomes `expired`. A
background sweeper checks every timeout/4 (1–30 s), and every lookup checks
lazily first. Expired Sessions answer REST with 410 and WebSocket joins with an
`expired` error and close code 4408; connected sockets get `closed {reason: expired}`.
A Session whose Rounds are running never expires (its timers keep it moving), so in
practice this hits abandoned Waiting Rooms and Sessions orphaned by a restart.

## Data model

Created on startup by `persistence.create_schema()`; changing a table needs
`docker compose down -v` (no migrations).

| Table | Columns |
|---|---|
| `sessions` | `id`, `room_code` (unique), `condition`, `status` (`waiting`/`active`/`completed`/`expired`), `incomplete`, `created_at`, `last_activity`, `expires_at`, `completed_at`, `decision_maker` (letter), `decided_by_tiebreak` |
| `participants` | `id`, `session_id`, `player_label` (letter, unique per Session), `type` (`human`/`ai`), `joined_at`, `last_activity`, `dropped_out_at` |
| `rounds` | `session_id`, `round_number` (1–2), `discussion_start`, `discussion_end`, `voting_end`, `vote_results` (JSONB) |
| `votes` | `session_id`, `round_number`, `participant_id`, `target_participant` (nullable), `kind` (`vote`/`abstention`/`missing`), `cast_at` |
| `messages` | `session_id`, `round_number`, `phase`, `participant_id`, `text`, `sent_at` |

Player Labels are stored as letters (`A`) and sent to browsers as `Player A`.

## AI Agents

`ai_agents.py` subscribes to engine events like the hub, but sees only broadcast
frames (what any browser sees). On a Session's first `phase` frame it creates one
runner per AI Agent. A runner posts an opening message per Discussion Phase,
replies to each message from someone else with probability `reply_rate`, waits a
random delay before each message, respects the per-Phase cap, and votes once per
Voting Phase. All of these numbers live in `ai_agents:` in `config.yml`.

The LLM sits behind `LLMClient` (`write_message`, `choose_vote`):

- **Mock** (`mock_mode: true`, default): scripted casual lines with random
  variation and a random Vote. Needs no network and no environment variables.
- **OpenAI-compatible** (`mock_mode: false`): `POST {LLM_BASE_URL}/chat/completions`
  with the prompts from `config.yml`. Works with hosted APIs and local servers such
  as Ollama.

Failures never stall a Session: a failed or unusable chat answer skips that
message; an unparseable vote answer becomes a random Vote. Answers are cached per
AI Agent and conversation state for the life of the Session (SPEC.md: "cache
responses per participant state"). Prompts, parameters and post-processing are in
[ai_prompts.md](ai_prompts.md).

## Known limitations

- **Live Session state is in memory.** The current Phase, deadline and who has
  voted live in the app process; the database holds the record. Restarting the
  app container mid-Session ends that Session: its row stays `active` until the
  inactivity sweeper marks it `expired`. One app process only (no horizontal scaling).
- **AI Agents keep going without Humans.** If every Human drops out, the AI
  Agents still chat and vote and the Session runs to its Result (flagged
  `incomplete`). Their activity also keeps the Session from expiring.
- **"Can't rejoin" wording depends on `localStorage`.** The server refuses every
  rejoin. Only the message differs: a different browser, a private window or
  cleared site data shows "already started" instead of "can't rejoin".
- **Manual start with free Human slots.** `POST /api/sessions/{rc}/start` only
  adds the Condition's AI Agents, so a Session forced to start early runs with
  fewer than three Participants. Meant for testing.
- **Config changes need a restart**, and they apply to the whole app. A Session
  keeps the Condition it was created with, but timings, AI Agent settings and
  the reveal setting are read from the config at the time.
- **Tie-break is random**, not smarter (SPEC.md: "arbitrary winner").
- **No authentication** beyond unguessable Room Codes, no LLM rate limiting, and
  simple console logs (all out of scope per SPEC.md).
- **Thinking models** need `reasoning_effort: none` (e.g. qwen3.5 on Ollama) or a
  much larger `max_tokens`; some providers reject that parameter, so it is off by default.
