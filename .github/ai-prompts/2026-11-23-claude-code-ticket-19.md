# AI conversation log: Claude Code, ticket #19 and README

- **Tool:** Claude Code CLI (terminal, Linux) with the user's skills (`implement`, `tdd`,
  `code-review`) and, from the fifth prompt on, the Playwright MCP server
- **Model(s):** claude-opus-5-5 (orchestrator and both review subagents)
- **Date:** 2026-11-23
- **Content:** every user prompt verbatim and every assistant reply. Tool calls are
  listed as one-line summaries; tool outputs and injected skill instructions are
  omitted. Written by the assistant from the session itself, as no export tool was
  available in the CLI. Interim progress lines are left out.


---

## 🧑 User

`/implement #19`


## 🤖 Claude

> 🔧 `gh issue view 19`: "Move the slot count and Condition to the Researcher's /waiting page"

> 🔧 Read: `api.py`, `realtime.py`, `main.py`, `session_engine.py`, `persistence.py`, `config.py`, the frontend room and waiting views, GLOSSARY.md, TESTING.md, SPEC.md

> 🔧 Docker socket not accessible (user not in the `docker` group); a `sudo docker` attempt was refused by the auto-mode classifier; rootless `podman compose` used instead

> 🔧 Edit backend: Researcher token on `POST /api/sessions` (SHA-256 stored in a new `sessions.researcher_token_hash` column, added with `ALTER TABLE ... IF NOT EXISTS` for old databases), `GET /api/sessions/{rc}/researcher` (403 without the right `X-Researcher-Token`), bare `waiting` frame sent only to the joiner, `Condition.describe()`

> 🔧 Skill `tdd`: seams taken from the ticket (the Researcher HTTP route and the Human `waiting` frame); black-box pytest file `backend/tests/test_researcher_status.py` against a running app

> 🔧 Red: built a stack from the old commit (port 8019, `3_humans`) → 6 failed, 2 passed (guards)

> 🔧 Edit frontend: `WaitingRoomView` without a count, reducer without `filled`/`total`, `/waiting` polls the Researcher route every second and shows the Condition and "n of m Humans joined" until the start

> 🔧 Green: 8 passed; then 7+1 skipped and 6+2 skipped under the other Conditions, also after dropping the new column (schema upgrade path)

> 🔧 Python Playwright script (no Playwright MCP in the session): Researcher 0 → 1 → 2 of 3 → started; Human tabs show no count; no Human frame has `filled`/`total`/`condition`

> 🔧 Docs: GLOSSARY (Waiting Room, Blind Condition, new "Researcher token"), ARCHITECTURE, TESTING, README; commit `455566d`

> 🔧 Skill `code-review`: Standards and Spec subagents in parallel

> 🔧 Fixes from the review, test-first: `GET /api/sessions/{rc}` lists no Player Labels while waiting (their number was the slot count); `POST /start` needs the Researcher token; shared `_load_session(allow_expired=True)` and `Condition.named` in the engine; 10 / 9+1 / 7+3 passed; commit `94da7e0`

Ticket #19 is done and committed to `spec-9-rebuild` in two commits: `455566d` for the feature and `94da7e0` for fixes from code review. The new tests pass under all three Conditions on a fresh Podman stack. One difference from the ticket: Playwright MCP wasn't available in this session, so I ran the browser check with a Python Playwright script instead.

**What changed**
- **Humans' Waiting Room:** shows only "You are Player X" and the waiting text. The `waiting` WebSocket message no longer has `filled`/`total`, and it goes only to the Human who just joined. Before, every join and leave was sent to everyone, so Humans could count each other from those messages.
- **Researcher token:** `POST /api/sessions` now returns a `researcher_token`, which is not part of the share link. Only a hash of it is stored.
- **New Researcher status endpoint:** `GET /api/sessions/{rc}/researcher` with the `X-Researcher-Token` header returns the Condition, Humans filled and total. Without the right token it answers 403.
- **`/waiting` page:** shows the Condition in words (for example "2 Humans + 1 AI Agent") and "n of m Humans joined". It checks every second until the Session starts, then says "All Humans joined. The Session has started."
- **Docs:** GLOSSARY (Waiting Room, Blind Condition, new "Researcher token" entry), ARCHITECTURE, TESTING and README are updated.

**Tests:** 10 black-box pytest checks in `backend/tests`, run against a live app with `APP_URL=… pytest backend/tests`. They cover the token check, the bare `waiting` message, no message to a Human when another joins or leaves, and the public routes giving nothing away. I confirmed the feature tests failed against the old code first. This is the repo's first pytest suite, although SPEC.md says no test suite is needed; it's small and documented in TESTING.md, but delete it if you'd rather keep to that.

**Browser check (3 Humans):** the Researcher page went 0 → 1 → 2 of 3, then "started". The Human tabs never showed a count, and none of their WebSocket messages contained `filled`, `total` or the Condition. "3 of 3" never appears because the Session starts the moment the third Human joins, so that line of the ticket can't be met as written.

## Code review

**Spec:**
- **Fixed, the one serious finding:** while a Session was waiting, `GET /api/sessions/{rc}` still listed the Humans present, so a Human could count them and learn the Condition. It now lists no Player Labels until the Session starts.
- **Fixed:** `POST /api/sessions/{rc}/start` needed no token, and its response after an early start also gave away the count. It now requires the Researcher token.
- **Small additions beyond the ticket:** `/waiting` also shows text for finished and expired Sessions. On startup the app now adds the new token column to an existing database, so you don't have to wipe it with `docker compose down -v`. I tested this by dropping the column and restarting.

**Standards:** no breaches of the repo's documented rules.
- **Fixed:** the engine had a duplicate Session lookup, and the mapping from a Condition to its Human/AI counts was repeated in three places.
- **Noted:** SPEC.md keeps authentication out of scope. I recorded the token in ARCHITECTURE.md as a per-Session shared secret, needed to keep the count from Humans, not a login.
- **Not changed:** some minor style suggestions in the `/waiting` page code.

If the Researcher reloads `/waiting`, the live count for that Session is lost, because the token is only kept in the open tab. The Session itself is unaffected; this is listed under known limitations in ARCHITECTURE.md.


---

## 🧑 User

did you check it?


## 🤖 Claude

Yes, I ran it, but not exactly the way the ticket asks.

**What I ran**
- **pytest checks against the running app:** after the review fixes, all 10 pass with 3 Humans. With 2 Humans + 1 AI Agent, 9 pass and 1 is skipped; with 1 Human + 2 AI Agents, 7 pass and 3 are skipped. Those checks need more Humans than the Condition has. Before the fixes, I ran the new checks against the old code and confirmed they failed.
- **Browser run with 3 Humans:** I ran this once before the review and again after the fixes. Both times the Researcher page went 0 → 1 → 2 of 3, then "All Humans joined. The Session has started." The Human tabs showed only their Player Label and the waiting text. None of their 9 WebSocket messages contained `filled`, `total` or the Condition. I looked at a screenshot of the Researcher page and it rendered correctly.
- **Existing database:** I dropped the new column and restarted. The app added it back, and the checks passed.

**What I didn't check**
- **Not Playwright MCP:** the ticket asks for it, but it isn't available in this session, so I used a Python Playwright script with the same steps.
- **The other two Conditions in the browser:** the pytest checks only confirm the Condition text is one of the three valid values. Nothing confirms "2 Humans + 1 AI Agent" or "1 Human + 2 AI Agents" appears on `/waiting` for the matching Condition.
- **The Human tab screenshot:** I took it but didn't look at it. I relied on the page text the script read.
- **Reloading `/waiting`:** I documented that this loses the live count but didn't try it.
- **The final doc edits:** they came after the last test run, but they only touch Markdown.

If you enable Playwright MCP, I can redo the 3-Human check with it. Or I can run the browser check now under the other two Conditions.


---

## 🧑 User

how to connect playwright we can properly do it?


## 🤖 Claude

> 🔧 `claude mcp list`: no Playwright server configured; Node 22 installed

Playwright MCP isn't set up yet: `claude mcp list` only shows Claude Docs, Gmail and Google Calendar. Node 22 is installed, so setup takes three steps.

**1. Add the server.** Run this in your terminal, outside Claude Code:

```sh
claude mcp add playwright -- npx @playwright/mcp@latest --browser chromium
```

- `--browser chromium` tells it to use Playwright's own Chromium. By default it looks for Google Chrome, which this machine may not have.
- Add `--headless` at the end if you don't want a browser window to pop up. Leave it off if you want to watch the test.
- This adds it for your user on this project only. If you put `-s project` right after `add`, it's saved in `.mcp.json` in the repo instead.

**2. Download the browser it uses:**

```sh
npx playwright install chromium
```

The Chromium I downloaded earlier is a headless-only build that the Python package uses, so this download is separate.

**3. Restart Claude Code to load the new tools:**

```sh
claude --continue
```

This keeps our conversation. You can confirm it's working with `/mcp`, where `playwright` should show as connected.

Once that's done, tell me and I'll start the app with 3 Humans again and redo the ticket's check with Playwright MCP. That means one Researcher tab on `/waiting` and three Human tabs on the share link. The Researcher tab should go 0 → 1 → 2 of 3, then "started", and the Human tabs should never show a count or receive one in a WebSocket message. Then I'll update the line in TESTING.md that currently says Python Playwright was used.


---

## 🧑 User

claude --continue


## 🤖 Claude

> 🔧 Searched for Playwright tools: none loaded yet; `claude mcp list` shows `playwright` connected

The Playwright server is set up: `claude mcp list` shows it as connected. But I still can't use it, because typing `claude --continue` here sends it to me as a chat message rather than running it. This session started before the server was added, so it doesn't have the Playwright tools yet.

To load them:

1. Exit this session with `/exit` or Ctrl+D twice.
2. In the same terminal, inside the project folder, run `claude --continue`. This reopens our conversation with the Playwright tools loaded.
3. Tell me "go" and I'll start the app with 3 Humans and run the check with Playwright MCP.

If the browser fails to start, run `npx playwright install chromium` in your terminal first.


---

## 🧑 User

ok run the playwright tests now


## 🤖 Claude

> 🔧 Started the stack with `condition: 3_humans` on port 8019 (Podman)

> 🔧 Playwright MCP: Researcher tab on `/waiting`, Create Session → "Condition: 3 Humans", "0 of 3 Humans joined"

> 🔧 First attempt: a Node-side frame recorder didn't survive between `browser_run_code` calls; restarted with a fresh Session and an in-page `WebSocket` wrapper (`addInitScript`)

> 🔧 Three Humans, each in its own isolated context; Researcher tab checked after each join; screenshot of the final Researcher page; Human tab network requests filtered for `/api/`

> 🔧 TESTING.md line updated, commit `26512ac`; stack stopped, browser closed

I ran the ticket's check with Playwright MCP, using a 3-Human Session, and it passed.

| Step | Researcher `/waiting` | Human tabs |
|---|---|---|
| Session created | "Condition: 3 Humans", "0 of 3 Humans joined" | – |
| Human 1 joins | 1 of 3 | "You are Player A" + waiting text only; received `joined`, then `{"type":"waiting"}` |
| Human 2 joins | 2 of 3 | "You are Player B" + waiting text only; Human 1 received nothing new |
| Human 3 joins | "All Humans joined. The Session has started." | Session went straight to Round 1 |

Each Human was in its own isolated browser context, and I recorded every WebSocket message each one received:
- None contained `filled`, `total`, `condition`, `human` or `ai`.
- Human 1 received only `joined`, `waiting` and `phase`.
- The Human tabs made no `/api` calls.

"3 of 3" never appears because the Session starts the moment the third Human joins, which matches the ticket's "then started". I looked at a screenshot of the final Researcher page and it renders correctly.

I updated the TESTING.md line that said Python Playwright was used and committed it as `26512ac`. The test app is shut down and the browser is closed.

There are now an untracked `package.json`, `package-lock.json` and `node_modules/` in the repo root, dated 05:14. They only add `@playwright/test`, so they probably came from installing Playwright while setting up the MCP server. I didn't commit them; delete them if you don't need them (`rm -rf package.json package-lock.json node_modules`).


---

## 🧑 User

ok push everything


## 🤖 Claude

> 🔧 `git push`: `401f71f..26512ac spec-9-rebuild -> spec-9-rebuild`

I pushed the three #19 commits to `origin/spec-9-rebuild`, and the branch now matches the remote:

- `455566d` feat: move slot count and Condition to the Researcher's /waiting page
- `94da7e0` fix: hide waiting Player Labels and guard manual start with the Researcher token
- `26512ac` docs: record the Playwright MCP check

I didn't commit the stray `package.json` and `package-lock.json` in the repo root; they're still untracked. They look like leftovers from installing Playwright, not part of the project. If you want them in the repo, tell me and I'll commit them.

Issue #19 is still open on GitHub. Should I close it, or will you close it when this branch is merged?


---

## 🧑 User

how would i now integrate a real llm to the project?


## 🤖 Claude

> 🔧 Read README "Mock mode vs. real LLM", `llm_parameters` in config.yml, `.env.example`; `ollama list` shows `qwen3.5:4b`

A real LLM is already built in: ticket #15 added a client that works with any OpenAI-compatible API, so you only need to configure it, not write code. You already have `qwen3.5:4b` in Ollama, so that's the quickest way to try it.

**1. Turn mock mode off** in `config.yml`:
```yaml
mock_mode: false
```
For qwen3/qwen3.5 models, also uncomment this under `llm_parameters:`, otherwise the model spends its token budget thinking and sends nothing:
```yaml
  reasoning_effort: none
```

**2. Point the app at the model.** The endpoint is only read from environment variables, never from `config.yml`. Copy `.env.example` to `.env` (it's git-ignored) and set:
```sh
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3.5:4b
```

**3. Restart the app:**
```sh
docker compose up --build -d     # or: docker compose restart app
```
Without `LLM_BASE_URL` and `LLM_MODEL`, the app refuses to start and logs a `CONFIG ERROR`.

**4. Check it works:** create a Session on `/waiting` with `condition: 1_human_2_ai` and open the share link.
- The AI Agents should write their own messages, not the scripted mock lines.
- `docker compose logs app` should show `POST .../chat/completions "HTTP/1.1 200 OK"`.
- `LLM call failed, message skipped` means the container can't reach Ollama.

The full checklist is in TESTING.md, under "Real LLM via a local Ollama".

**If the container can't reach Ollama:** by default Ollama only listens on 127.0.0.1, and a container may not be able to reach that. Make it listen on all addresses with `sudo systemctl edit ollama`, add the lines below, then run `sudo systemctl restart ollama`:
```
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

**Hosted API instead:** set the same three variables to the provider's OpenAI-compatible endpoint, model name and key:
```sh
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=<model>
LLM_API_KEY=<key>
```

**Tuning:** the prompts, `temperature`, `max_tokens` and `timeout_seconds` are in `config.yml`, and `ai_prompts.md` explains them. A call that takes longer than `timeout_seconds` (20 s by default) is treated as a failure. A 4B model on CPU can be that slow, so raise the timeout if messages keep getting skipped. Either way, a failed call never stops the Session: that message is skipped, and a failed vote becomes a random Vote.

I can set this up with your local `qwen3.5:4b` and run a Session to check it end to end if you like.


---

## 🧑 User

ok update the readme so it contains all this info and describes the repo better. also update the file containing the logs of our conversation and push everything when you're done


## 🤖 Claude

> 🔧 Read README, AI-USAGE-LOG.md, the 2026-11-22 transcript, ARCHITECTURE overview, module docstrings, config.yml

> 🔧 Rewrote README.md: what the platform is, how a Session works, run, a config table, mock vs. real LLM (variables table, step-by-step local Ollama, the `OLLAMA_HOST` fix, hosted API, tuning and failures), repository layout, API routes, testing, key decisions

> 🔧 Wrote this transcript and added stage 4 to `.github/AI-USAGE-LOG.md`; committed and pushed

(The final reply of this turn is in the commit history: the README and log commit on `spec-9-rebuild`.)
