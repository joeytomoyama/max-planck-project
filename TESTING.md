# Testing

Per SPEC.md there is no unit/integration test suite and no CI. The app is tested
end to end in a real browser with **Playwright MCP** (driven by the coding agent),
plus the manual checklist below for what that does not cover, and a few black-box
checks (see [Automated checks](#automated-checks-researcher-token)).

## Setup for a test run

Use mock mode (the default) and short timings so a Session takes about a minute:

```yaml
# config.yml (put the defaults back afterwards)
timings:
  discussion_seconds: 15
  voting_seconds: 10
  inactivity_timeout_minutes: 0.25   # only for the expiry test
```

```sh
docker compose up --build -d        # or: docker compose restart app after editing config.yml
```

A separate stack next to a running one: `APP_PORT=8017 docker compose -p t17 up --build -d`
and `docker compose -p t17 down -v` afterwards. Each simulated Human is a
separate browser context or tab; closing it is a disconnect.

## Covered with Playwright MCP

Checked against the running app while building tickets #10–#17. Assertions are on
what a Participant sees (Player Label, chat, Phase and countdown, "Your vote has
been recorded", the Result), plus captured network traffic for the Blind Condition.

| Flow | Conditions |
|---|---|
| Waiting Room fills from empty and the Session starts on its own; the Researcher's `/waiting` shows the Condition and goes "0 → 1 → 2 → 3 of 3 Humans joined" → "started", while the Human tabs show no count and no Human WS frame has `filled`/`total` (#19; Python Playwright, Playwright MCP was unavailable) | all three (count flow: 3_humans) |
| Share link, Player Label shown ("You are Player X"), random labels | all three |
| Discussion Rounds progress, countdown runs, chat appears in every tab, input closes when the Phase ends | 3_humans, 2_humans_1_ai, 1_human_2_ai |
| AI Agents (mock) post an opening message, reply, stay under the cap, vote | 2_humans_1_ai, 1_human_2_ai |
| Voting: only "Your vote has been recorded" after Round 1, early end once all voted, Result with combined counts and Decision Maker | all three |
| "This Session has already started" for a late joiner, "Session not found" for a bad Room Code | 2_humans_1_ai |
| Session timeout: an expired Session's link shows "This Session has expired" | 3_humans |
| A Human closes their tab mid-Session: the others continue and reach the Result; reopening shows "You can't rejoin this Session" | 3_humans |
| Blind Condition: no `human`/`ai`/`types` in any WebSocket frame or REST body (`/api/sessions`, `/api/sessions/{rc}`, `/config`) before the Result, none in the Result with reveal off | 2_humans_1_ai, 1_human_2_ai |
| Real LLM via local Ollama (`qwen3.5:9b`) and a stub returning garbage / HTTP 500 / "As an AI…" | 1_human_2_ai |
| README walkthrough: run on `APP_PORT`, create a Session, play it to the Result in mock mode; switch the Condition with `docker compose restart app` | 2_humans_1_ai, then 3_humans |
| Votes cast within milliseconds of the Voting deadline (raw WebSockets, many Sessions): every `vote_recorded` Vote is in the Result and `rounds.vote_results`, later ones get `vote_closed`; a Human disconnecting just after the deadline gets an Abstention, just before it `missing` | 3_humans |
| A Dropout's Player Label stays in `GET /api/sessions/{rc}` (once active); a second `join` frame gets `error` `already_joined` | 2_humans_1_ai |
| AI Agents (mock, `reply_rate: 1`, several quick Human messages) never post the same line twice in a row | 1_human_2_ai |
| `mock_seed: 42`: Sessions with the same Player Labels and no Human chat give identical AI Agent messages and Result, also after an app restart | 1_human_2_ai |

## Automated checks: Researcher token

`backend/tests` holds black-box pytest checks that talk to a running app over HTTP
and WebSocket: the Researcher token (refused without it, with a wrong one or
another Session's; Condition and slots with the right one), no Condition or slot
count in the public REST routes (no Player Labels while waiting), manual start
only with the token, and a Human's `waiting` frame being exactly
`{"type": "waiting"}` with no frame to them when another Human joins or leaves.

```sh
docker compose up --build -d
pip install -r backend/requirements-dev.txt
APP_URL=http://localhost:8000 pytest backend/tests
```

Some checks need more Human slots and skip otherwise; run once with
`condition: 3_humans` to cover all of them.

## Manual checklist

### Invalid `condition:` stops startup

1. Set `condition: 4_humans` in `config.yml`, then `docker compose up` (or `restart app`).
   - [ ] The app container exits; `docker compose logs app` shows
         ``CONFIG ERROR: Invalid `condition: 4_humans` in config.yml. Valid options: 3_humans | 2_humans_1_ai | 1_human_2_ai``.
2. Delete the `condition:` line.
   - [ ] ``CONFIG ERROR: Missing `condition:` in config.yml. Valid options: ...``
   - [ ] Same message with `mock_mode: false` and no LLM env vars (the Condition is checked first).
3. Put the valid value back and restart.
   - [ ] The app starts and logs `Started with condition=...`.

### Switching Conditions

For each of `3_humans`, `2_humans_1_ai`, `1_human_2_ai`: edit `condition:`, run
`docker compose restart app`, create a new Session.
- [ ] `/waiting` shows `Condition: 3 Humans`, `2 Humans + 1 AI Agent` or
      `1 Human + 2 AI Agents`, and `0 of 3`, `0 of 2` or `0 of 1 Humans joined`.
- [ ] The Session starts when that many tabs have joined, and `/waiting` then says
      it has started.
- [ ] The Human tabs show only "You are Player X" and "Waiting for others to join",
      never a count.

### Real LLM via a local Ollama

1. Install [Ollama](https://ollama.com) on the host and pull a model, e.g.
   `ollama pull qwen3.5:9b`. Check it answers:
   `curl http://localhost:11434/v1/models`.
2. In `config.yml` set `mock_mode: false` and `condition: 1_human_2_ai`. For a
   thinking model (qwen3 family) uncomment `reasoning_effort: none` under
   `llm_parameters:`.
3. Start with the LLM env vars (or put them in `.env`):
   ```
   LLM_BASE_URL=http://host.docker.internal:11434/v1 LLM_MODEL=qwen3.5:9b docker compose up --build
   ```
   PowerShell: `$env:LLM_BASE_URL="http://host.docker.internal:11434/v1"; $env:LLM_MODEL="qwen3.5:9b"; docker compose up --build`
4. Open `/waiting`, create a Session, open the share link in another tab.
   - [ ] Both AI Agents post an opening message in each Discussion Phase, in
         short casual English that fits the chat (not the mock lines from
         `backend/app/llm.py`).
   - [ ] Writing "are you a bot?" gets no admission of being an AI.
   - [ ] The app log shows `POST .../chat/completions "HTTP/1.1 200 OK"` and, at
         voting, no `votes at random` lines (the LLM's Vote was parsed).
   - [ ] The Session reaches the Result.
5. Failure path: stop Ollama (or set `LLM_BASE_URL` to a port nothing listens
   on) and run another Session.
   - [ ] AI Agents send nothing, the log shows `LLM call failed, message skipped`
         and `votes at random`, and the Session still reaches the Result.
6. Without `LLM_BASE_URL`/`LLM_MODEL` and with `mock_mode: false`:
   - [ ] the app refuses to start with a `CONFIG ERROR` naming the missing env vars.
7. Put `mock_mode: true` back.

A hosted API works the same way with its own `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.

### Reveal on vs. off

1. `reveal_identities_at_end: false` (default), `condition: 2_humans_1_ai`. Play a
   Session to the end with the browser's DevTools Network tab open (WS frames).
   - [ ] The Result shows only Player Labels, counts and the Decision Maker.
   - [ ] No frame or response contains `"types"`, `"human"` or `"ai"`.
2. Set `reveal_identities_at_end: true`, `docker compose restart app`, play again.
   - [ ] The Result shows "Human" / "AI Agent" next to each Player Label, and it matches
         `participants.type` in the database.
   - [ ] Only the `result` frame carries `types`; earlier frames are unchanged.
3. Put `false` back.

### Inspecting stored rows

```sh
docker compose exec db psql -U mpp -d mpp
```

```sql
select id, room_code, condition, status, incomplete, decision_maker, decided_by_tiebreak,
       created_at, completed_at, expires_at from sessions order by id desc limit 5;
select session_id, player_label, type, joined_at, dropped_out_at from participants
  where session_id = <id> order by player_label;
select round_number, discussion_start, discussion_end, voting_end, vote_results
  from rounds where session_id = <id> order by round_number;
select round_number, participant_id, kind, target_participant, cast_at
  from votes where session_id = <id> order by round_number, participant_id;
select round_number, phase, participant_id, text, sent_at from messages
  where session_id = <id> order by sent_at;
```

After a completed Session:
- [ ] `status = completed`, `decision_maker` set, `decided_by_tiebreak` true only if
      the top count was shared.
- [ ] One `participants` row per Player Label with the right `type` for the Condition.
- [ ] Two `rounds` rows with timestamps and `vote_results` counts that add up to the Result.
- [ ] One `votes` row per Participant per Round: `vote`, `abstention` (present, did not
      vote in time) or `missing` (Dropout).
- [ ] AI Agent and Human messages stored alike, each with Round, Phase and time.

After a Session with a Dropout (close one tab during Round 1):
- [ ] `sessions.incomplete = true`, the Dropout has `dropped_out_at`, and their Votes
      are `missing` (not `abstention`) for the Rounds they missed.

## Skipped scenarios

| Scenario | Why skipped |
|---|---|
| Network failures, flaky connections, database timeouts | Out of scope in SPEC.md ("complex error handling"). A lost socket is simply a Dropout. |
| Tie-breaking edge cases (e.g. 2–2–2 or no Votes at all) | The rule is an arbitrary pick (SPEC.md); it lives in the pure `vote_tally.tally` and is hard to force through the UI. Ties do occur in normal runs and show up as `decided_by_tiebreak`. |
| App restart in the middle of a Session | Known limitation: live state is in memory, so the Session is lost and later expires (see ARCHITECTURE.md). Only the expiry of such an orphaned row was checked, by inserting one with psql. |
| Many concurrent Sessions / load | Single-process research tool; no load target in SPEC.md. |
| LLM rate limits and slow endpoints under load | Out of scope (SPEC.md trade-off 3). A call slower than `timeout_seconds` is treated as a failure. |
| "This Session is full" view | The Session starts the moment its last Human slot fills, so a further joiner normally sees "already started"; "full" only appears in a narrow race and was not forced. |
| Cross-browser and mobile layouts | Only Chromium (Playwright MCP) was used. |
| Unit tests for engine and tally | No test suite per SPEC.md; behaviour is checked through the browser. |
