# Human-AI Group Decision Experiment

A web platform for a 3-Participant experiment: Humans and AI Agents chat for two
Rounds and vote on who should be the Decision Maker, without knowing who is
human (the Blind Condition). FastAPI + React + PostgreSQL, started with one command.

Requirements: [SPEC.md](SPEC.md) and spec issue #9 (tickets #10-#17). Terms: [GLOSSARY.md](GLOSSARY.md).
More: [ARCHITECTURE.md](ARCHITECTURE.md), [TESTING.md](TESTING.md),
[ai_prompts.md](ai_prompts.md) (AI Agent prompts), [AI Usage Log](.github/AI-USAGE-LOG.md).

## Run

```sh
docker compose up --build
```

Open <http://localhost:8000/waiting>, click **Create Session** and share the link
(`/room/<Room Code>`) with the Humans. The Session starts by itself when the last
Human slot fills; AI Agents take the remaining slots.

- Other host port: `APP_PORT=8080 docker compose up --build`
  (PowerShell: `$env:APP_PORT="8080"; docker compose up --build`), or set it in `.env`.
- Data stays in the `pgdata` volume. `docker compose down -v` deletes it.
- Playing several Humans yourself: open the link once per Human, in separate tabs or windows.

## Switch Conditions

Edit the one `condition:` line in [`config.yml`](config.yml), then restart:

```yaml
# Valid values: 3_humans | 2_humans_1_ai | 1_human_2_ai
condition: 2_humans_1_ai
```

```sh
docker compose restart app
```

No rebuild is needed (`config.yml` is mounted into the container). An invalid or
missing value stops the app with a `CONFIG ERROR` that names the bad value and the
valid options (see `docker compose logs app`). The same file holds the Phase timings, AI Agent
behaviour, prompts and `reveal_identities_at_end` (off by default; turn it on to
show who was Human or AI on the Result). Sessions keep the Condition they were created with.

## Mock mode vs. real LLM

**Mock mode** (`mock_mode: true`, the default) needs no LLM and no environment
variables: AI Agents send scripted, slightly varied casual messages and vote at random.
For repeatable demos set `mock_seed: <number>` in `config.yml`: with the same
Player Labels and Human messages, AI Agents then write and vote the same way every time.

**Real LLM**: any OpenAI-compatible endpoint. Set `mock_mode: false` and pass the
endpoint through environment variables (never `config.yml`), e.g. in `.env`
(copy [`.env.example`](.env.example)):

```sh
LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=<model> LLM_API_KEY=<key> docker compose up --build
```

**Local Ollama** (free, no key): `ollama pull qwen3.5:9b`, then

```sh
LLM_BASE_URL=http://host.docker.internal:11434/v1 LLM_MODEL=qwen3.5:9b docker compose up --build
```

For thinking models such as qwen3/qwen3.5, uncomment `reasoning_effort: none` under
`llm_parameters:` in `config.yml`; otherwise they spend the token budget thinking.
With `mock_mode: false` and no `LLM_BASE_URL`/`LLM_MODEL` the app refuses to start.
Step-by-step checks: [TESTING.md](TESTING.md#real-llm-via-a-local-ollama).

## Key decisions and trade-offs

- **One app image + PostgreSQL.** SPEC.md contradicts itself (two containers vs.
  React served by FastAPI); we followed the majority: a multi-stage build serves the
  React build from FastAPI. No reverse proxy, no separate frontend container.
- **Server owns every timer.** Discussion 60 s, Voting up to 20 s (ends early once
  every connected Participant has voted). Clients only display the countdown.
- **Blind Condition enforced on the server.** Only Player Labels (Player A/B/C,
  assigned at random) ever leave the server; no REST response or WebSocket frame
  carries a Participant's type, except the Result when the reveal is on. AI Agent
  messages and Votes go through the same code path as Human ones. No typing indicators.
- **Voting ([ADR 0001](docs/adr/0001-voting-design-for-human-vs-ai-choice.md)).**
  Self-votes allowed, Round 1 results hidden ("Your vote has been recorded" only),
  the Decision Maker has the most Votes across both Rounds; ties get an arbitrary
  (random) pick, stored as `decided_by_tiebreak`.
- **Dropouts.** A Human who disconnects after the start (a refresh counts) is a
  Dropout: cannot rejoin, missed Votes stored as `missing` (not Abstentions), the
  Session continues and is flagged `incomplete`.
- **Room Codes** are random URL-safe tokens (~72 bits); no other auth.
- **Testing** is Playwright MCP against the running app plus the manual checklist in
  TESTING.md. No unit test suite or CI, per SPEC.md.

Known limitations are listed in [ARCHITECTURE.md](ARCHITECTURE.md#known-limitations).
