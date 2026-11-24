# Human-AI Group Decision Experiment

A research platform for a three-person group decision experiment. Three Participants
(some Humans, some AI Agents) chat for two Rounds, then vote on who among them should
be the Decision Maker. Nobody can tell from the platform who is human: everyone is
just "Player A", "Player B" or "Player C" (the **Blind Condition**). The Researcher
picks the mix of Humans and AI Agents (the **Condition**) and gets every message,
Vote and Result stored in PostgreSQL for analysis.

FastAPI + React + PostgreSQL, started with one command. AI Agents run in mock mode
by default (no LLM needed) or on any OpenAI-compatible LLM, local or hosted.

- Requirements: [SPEC.md](SPEC.md) (wins every conflict) and spec issue #9 (tickets #10–#17, #19)
- Domain terms: [GLOSSARY.md](GLOSSARY.md). This README uses them with capitals.
- Design: [ARCHITECTURE.md](ARCHITECTURE.md), voting rules in [ADR 0001](docs/adr/0001-voting-design-for-human-vs-ai-choice.md)
- Testing: [TESTING.md](TESTING.md)
- AI Agent prompts: [ai_prompts.md](ai_prompts.md)
- How AI was used to build this: [AI Usage Log](.github/AI-USAGE-LOG.md)

## How a Session works

1. **Create.** The Researcher opens `/waiting` and clicks **Create Session**. The page
   shows a share link (`/room/<Room Code>`), the active Condition (e.g.
   "2 Humans + 1 AI Agent") and a live "n of m Humans joined" count.
2. **Waiting Room.** Each Human opens the share link and sees only their Player
   Label ("You are Player B") and "Waiting for others to join". Humans never see a
   count or the Condition: it would tell them how many AI Agents there are.
3. **Start.** When the last Human slot fills, the Session starts on its own and AI
   Agents take the remaining Player Labels. The `/waiting` page then says it has started.
4. **Two Rounds.** Each Round is a Discussion Phase (chat, 60 s by default) and a
   Voting Phase (up to 20 s, ends early once everyone has voted). Every timer runs
   on the server. Round 1 Votes stay hidden ("Your vote has been recorded").
5. **Result.** The Participant with the most Votes across both Rounds becomes the
   Decision Maker (ties are broken at random). Optionally the Result reveals who was
   Human and who was an AI Agent.

A Human who disconnects after the start is a **Dropout**: they can't rejoin, the
Session goes on without them, and it is flagged as an Incomplete Session.

## Run

Needs Docker (or Podman) with Compose.

```sh
docker compose up --build
```

Open <http://localhost:8000/waiting>, click **Create Session** and share the link
with the Humans. To play several Humans yourself, open the link once per Human in
separate windows or private windows (a refresh after the start makes you a Dropout).

- Other host port: `APP_PORT=8080 docker compose up --build`
  (PowerShell: `$env:APP_PORT="8080"; docker compose up --build`), or set it in `.env`.
- Data stays in the `pgdata` volume; `docker compose down -v` deletes it.
- The Researcher's live count only lives in the `/waiting` tab that created the
  Session (it holds that Session's secret Researcher token). Reloading the tab loses
  the count, not the Session.

## Configuration (`config.yml`)

Everything about the experiment is in [`config.yml`](config.yml), mounted into the
container. After editing it, run `docker compose restart app` (no rebuild needed).
An invalid or missing value stops the app with a `CONFIG ERROR` naming the bad value
and the valid options (see `docker compose logs app`).

| Setting | What it does |
|---|---|
| `condition` | `3_humans`, `2_humans_1_ai` or `1_human_2_ai`. Sessions keep the Condition they were created with. |
| `timings` | Discussion and Voting Phase lengths, inactivity timeout before a Session expires |
| `mock_mode` | `true` (default): scripted AI Agents, no LLM. `false`: real LLM (see below). |
| `mock_seed` | Optional number that makes mock AI Agents repeatable for demos |
| `ai_agents` | How often AI Agents reply, their typing delay, message cap per Phase |
| `prompts` | The system, opening, reply and vote prompts sent to the LLM |
| `llm_parameters` | `temperature`, `max_tokens`, `timeout_seconds`, optional `reasoning_effort` |
| `reveal_identities_at_end` | Show "Human" / "AI Agent" on the Result (off by default) |

## AI Agents: mock mode or a real LLM

**Mock mode** (`mock_mode: true`, the default) needs no LLM, network or environment
variables. AI Agents send scripted, slightly varied casual messages and vote at
random. Use it to test the flow. With `mock_seed: <number>`, the same Player Labels
and Human messages give the same AI Agent messages and Votes every time.

**Real LLM**: the app talks to any **OpenAI-compatible** chat completions endpoint
(`POST {LLM_BASE_URL}/chat/completions`). The endpoint, model and key come only
from environment variables, never from `config.yml`:

| Variable | Required | Example |
|---|---|---|
| `LLM_BASE_URL` | yes | `http://host.docker.internal:11434/v1` |
| `LLM_MODEL` | yes | `qwen3.5:9b` |
| `LLM_API_KEY` | only if the endpoint needs one | `sk-...` |

Put them in `.env` (copy [`.env.example`](.env.example); `.env` is git-ignored) or
pass them on the command line. With `mock_mode: false` and no `LLM_BASE_URL` /
`LLM_MODEL`, the app refuses to start.

### Local LLM with Ollama (free, no key)

1. Install [Ollama](https://ollama.com) on the host and pull a model:
   `ollama pull qwen3.5:9b` (any model you have works; `ollama list` shows them).
   Check it answers: `curl http://localhost:11434/v1/models`.
2. In `config.yml` set `mock_mode: false`. For thinking models (the qwen3 / qwen3.5
   family) also uncomment `reasoning_effort: none` under `llm_parameters:`, or they
   spend the whole token budget thinking and send nothing.
3. In `.env`:
   ```sh
   LLM_BASE_URL=http://host.docker.internal:11434/v1
   LLM_MODEL=qwen3.5:9b
   ```
4. `docker compose up --build -d` (or `docker compose restart app` if it is running).
5. Check: create a Session with `condition: 1_human_2_ai` and open the share link.
   The AI Agents should write their own messages (not the mock lines), and
   `docker compose logs app` should show `POST .../chat/completions "HTTP/1.1 200 OK"`.

**If the container can't reach Ollama** (the log shows `LLM call failed, message
skipped`): by default Ollama only listens on `127.0.0.1`, which a container may not
reach. Make it listen on all interfaces with `sudo systemctl edit ollama`, add

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

then `sudo systemctl restart ollama`. Small models on a CPU can also be slower than
`timeout_seconds` (20 s by default); raise it in `config.yml` if messages keep being skipped.

### Hosted API

Same three variables, with the provider's OpenAI-compatible endpoint, a model name
and your key, e.g.

```sh
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=<model>
LLM_API_KEY=<key>
```

### Tuning and failures

Prompts and parameters are in `config.yml`; [ai_prompts.md](ai_prompts.md)
explains each prompt, the request shape and how answers are cleaned up. A failed
LLM call never stops a Session: a failed message is skipped, and a Vote the app
can't parse becomes a random Vote. The full real-LLM checklist is in
[TESTING.md](TESTING.md#real-llm-via-a-local-ollama).

## Repository layout

```
backend/app/
  main.py            app factory: wires config, database, API, WebSocket hub, AI Agents, SPA
  config.py          loads and validates config.yml (CONFIG ERROR on bad values)
  session_engine.py  every game rule: Sessions, Waiting Room, Phases, timers, Votes, Dropouts, expiry
  api.py             REST routes under /api/sessions (thin, calls the engine)
  realtime.py        the WebSocket hub /ws/{room_code}: JSON frames in and out
  ai_agents.py       AI Agent runners: chat and vote through the same engine path as Humans
  llm.py             LLM client: mock, or OpenAI-compatible HTTP
  vote_tally.py      pure function from Votes to the Result
  persistence.py     PostgreSQL tables (created on startup)
backend/tests/       black-box pytest checks against a running app
frontend/src/
  views/             WaitingPage (Researcher, /waiting) and RoomPage (Participant, /room/:roomCode)
  room/              Waiting Room, Discussion, Voting, Result and error views, WebSocket hook
config.yml           the experiment settings
docker-compose.yml   app + PostgreSQL; Dockerfile builds React, then serves it from FastAPI
docs/adr/            architecture decision records
```

### API

| Route | Who | What |
|---|---|---|
| `POST /api/sessions` | Researcher | Create a Session: Room Code, share link, secret Researcher token |
| `GET /api/sessions/{room_code}/researcher` | Researcher (header `X-Researcher-Token`) | Condition, Human slots filled and total |
| `POST /api/sessions/{room_code}/start` | Researcher (token) | Force the start before all Humans joined (for testing) |
| `GET /api/sessions/{room_code}` | anyone with the Room Code | Status, Round, Phase; Player Labels once started |
| `GET /api/sessions/{room_code}/config` | anyone with the Room Code | Phase timings and number of Rounds |
| `WS /ws/{room_code}` | Humans | Join, chat, vote; Phase, chat and Result frames |
| `GET /api/health` | ops | App and database status |

Nothing a Human can reach carries a Participant's type, the Condition or the slot
count (only the Result, if the reveal is on, carries types).

## Testing

- **End to end** with Playwright MCP against the running app: every flow listed in
  [TESTING.md](TESTING.md), across the Conditions listed there.
- **Black-box checks** for the Researcher token and the Waiting Room:
  ```sh
  pip install -r backend/requirements-dev.txt
  APP_URL=http://localhost:8000 pytest backend/tests
  ```
- **Manual checklist** in TESTING.md for what isn't automated (config errors,
  switching Conditions, real LLM, reveal setting, stored rows).

There is no unit test suite or CI, per SPEC.md.

## Key decisions and trade-offs

- **One app image + PostgreSQL.** SPEC.md contradicts itself (two containers vs.
  React served by FastAPI); we followed the majority: a multi-stage build serves the
  React build from FastAPI. No reverse proxy, no separate frontend container.
- **Server owns every timer.** Clients only display a countdown to the server's deadline.
- **Blind Condition enforced on the server.** Only Player Labels (assigned at random)
  leave the server; no REST response or WebSocket frame carries a Participant's type,
  except the Result when the reveal is on. AI Agent messages and Votes go through the
  same code path as Human ones. No typing indicators.
- **The Researcher sees the Condition and the count, Humans don't.** The Room Code is
  in every Human's link, so the count comes from a route that needs a per-Session
  Researcher token (only its hash is stored). A shared secret, not a login: SPEC.md
  keeps authentication out of scope.
- **Voting ([ADR 0001](docs/adr/0001-voting-design-for-human-vs-ai-choice.md)).**
  Self-votes allowed, Round 1 results hidden, the Decision Maker has the most Votes
  across both Rounds, ties get a random pick stored as `decided_by_tiebreak`.
- **Dropouts** can't rejoin; their missed Votes are stored as `missing`, not as Abstentions.
- **Room Codes** are random URL-safe tokens (~72 bits), so Sessions can't be guessed.
- **Live Session state is in memory** (one app process); restarting the app mid-Session
  loses that Session.

More limitations: [ARCHITECTURE.md](ARCHITECTURE.md#known-limitations).
