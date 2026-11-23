# AI Usage Log - Max Planck Project

## Overview

This document tracks all AI-assisted development work done on the Max Planck Project: the
prompts, and the exact models and tools used. The AI Agents' own runtime prompts (what the
app sends to an LLM) are documented separately in [`ai_prompts.md`](../ai_prompts.md).

The project was built in three stages, followed by follow-up tickets:

| Stage | Dates | Tool | Model | Result |
|---|---|---|---|---|
| 1. First attempt (scrapped) | 2026-11-20 | opencode with the mattpocock-skills | `qwen3.5:9b` on a local Ollama | Tickets #1-#8 and code for #1-#3, kept on the `qwen-attempt` branch |
| 2. Review, restart and grilling | 2026-11-22 | Claude Code (Claude desktop app, Code tab) with the mattpocock-skills plugin | Claude Opus 5.5 (`claude-opus-5-5`) | Old code cleared, `GLOSSARY.md`, ADR 0001, spec issue #9, tickets #10-#17 |
| 3. Rebuild from spec #9 | 2026-11-22 to 2026-11-23 | Claude Code (Claude desktop app) with the mattpocock-skills plugin and the Playwright MCP server | Claude Opus 5.5 (`claude-opus-5-5`) for the orchestrator and every implementer subagent | The current code on `spec-9-rebuild`, one branch per ticket |
| 4. Ticket #19 and README | 2026-11-23 | Claude Code CLI (terminal) with the `implement`, `tdd` and `code-review` skills, then the Playwright MCP server | Claude Opus 5.5 (`claude-opus-5-5`) for the session and both review subagents | Slot count and Condition moved to the Researcher's `/waiting` page; README rewritten |

---

## Stage 1: Development Session: Nov 20, 2026 (first attempt, scrapped)

> Note added in stage 3: this section is the original log of the first attempt and is kept
> unchanged below for the record. The files it lists were removed from `main` in commit
> `be1418f` and survive only on the `qwen-attempt` branch; they do not describe the current
> code. The prompts below are the paraphrases written at the time; the raw opencode session
> was not exported.

### Model Used

- **Provider**: Ollama
- **Model**: qwen3.5:9b (or similar available model)

### Tasks Performed

All scaffolding and setup work for ticket #01 was AI-assisted via the implement skill framework.

#### Files Created with AI Assistance

**Docker & Infrastructure:**
- `docker-compose.yml` - Multi-service orchestration
- `.env.example` - Environment variable documentation
- `backend/Dockerfile` - Python + React build image
- `frontend/Dockerfile` - React build + nginx serve image

**Backend (FastAPI):**
- `backend/requirements.txt` - Dependencies
- `backend/src/main.py` - API endpoints, WebSocket handling, DB schema

**Frontend (React):**
- `frontend/package.json` - Node dependencies
- `frontend/public/index.html` - React entry point
- `frontend/src/index.js` - React root rendering
- `frontend/src/App.js` - Router, WaitingRoom/ExperimentRoom components
- `frontend/src/styles.css` - Basic styling

**Configuration:**
- `config/config.yml` - Participant type configurations
- `ai_prompts.md` - AI prompt documentation (spec requirement)

**Documentation:**
- `README.md` - Project overview and run instructions
- `ARCHITECTURE.md` - Design decisions and trade-offs
- `TESTING.md` - Manual verification checklist

### Prompts Used During Implementation

The following were key prompts (or prompt categories) used:

1. **"Set up Docker Compose with backend, frontend, PostgreSQL"**
   - Produced: `docker-compose.yml`, `.env.example`

2. **"Create FastAPI backend with WebSocket and REST endpoints"**
   - Producing: session management, chat broadcasting, room creation

3. **"Build React SPA with routes for /waiting and /room/:sessionId"**
   - Client-side routing, state management, real-time updates

4. **"Document all AI prompts in ai_prompts.md"**
   - Per spec requirement for transparency

### Models and Parameters

- **Mock Mode**: Enabled by default (`MOCK_LLM=true`)
- **Temperature**: 0.7 for creativity (when enabled)
- **Deterministic Testing**: Seed-based responses for reproducibility

---

## Stage 2: Review, restart and grilling (Nov 22, 2026)

- **Tool:** Claude Code in the Claude desktop app (Code tab), mattpocock-skills plugin
  (`ask-matt`, `grilling`, `domain-modeling`).
- **Model:** Claude Opus 5.5 (`claude-opus-5-5`).
- **Full transcript** (every user prompt verbatim, every reply, tool calls summarised):
  [`ai-prompts/2026-11-22-claude-code-review-and-grilling.md`](ai-prompts/2026-11-22-claude-code-review-and-grilling.md).

What happened, in order of the user's prompts:

1. `/mattpocock-skills:ask-matt` asking whether to code-review the qwen code and file
   improvement tickets. Claude rated the code about 4/10 (broken data model behind
   green tests that faked the database) and recommended a rebuild.
2. "No, just restart": the old code moved to the `qwen-attempt` branch, `main` cleared
   to the planning files (commit `be1418f`).
3. "Yes, grill me": a grilling session on every open design question. The user's rule
   "for any conflicts we follow the SPEC.md" reversed several earlier answers. Outcomes:
   `GLOSSARY.md`, [ADR 0001](../docs/adr/0001-voting-design-for-human-vs-ai-choice.md)
   (Round 1 hidden, both Rounds count, self-votes allowed), the Dropout and
   reveal-setting decisions, and the one-app-image decision (commit `98e080c`).
4. From those decisions, spec issue #9 ("Spec: Multi-participant Human-AI experiment
   platform (rebuild)") and its vertical-slice tickets #10-#17 were filed on GitHub,
   replacing the stale #1-#8. The issues themselves are the record of that output.

## Stage 3: Rebuild from spec #9 (Nov 22-23, 2026)

- **Tool:** Claude Code in the Claude desktop app, with:
  - the mattpocock-skills plugin: `implement-spec` (orchestration), `tdd`
    (red-green loop; here "tests" are browser checks, since SPEC.md rules out a test
    suite) and `code-review` (standards and spec review of each ticket),
  - the **Playwright MCP** server for end-to-end checks in a real Chromium against
    `docker compose up` (mock mode, shortened timings),
  - Docker Compose, `gh` (GitHub CLI) for reading the issues, git worktrees.
- **Model:** Claude Opus 5.5 (`claude-opus-5-5`) for the orchestrating session and for
  every implementer subagent. No other model was used for code in this stage.
- **AI Agent runtime model** (not a development tool): manual real-LLM checks used
  `qwen3.5:9b` on a local Ollama, see `ai_prompts.md`.

### Prompts

The user's prompt to the orchestrator was the skill command:

```
/mattpocock-skills:implement-spec #9
```

The orchestrator read spec #9 and its sub-issues and started one implementer
subagent per ticket, in dependency order, each in its own git worktree and branch
(`ticket-NN`), then merged the branch into the integration branch `spec-9-rebuild`.
Each implementer's prompt was the GitHub issue for its ticket (read with
`gh issue view`), plus the parent spec #9, SPEC.md (which wins any conflict),
`GLOSSARY.md`, ADR 0001, hand-over notes from the earlier tickets, and working rules
(start from `spec-9-rebuild`, use the `tdd` skill with Playwright MCP as the test
seam, use a separate Docker Compose project and port, small commits, no pushing).
The issues are the authoritative text of those prompts:

| Ticket | Issue title | Merge commit on `spec-9-rebuild` |
|---|---|---|
| #10 | App skeleton with config check | `deae9d3` |
| #11 | Create a Session and join the Waiting Room | `b40886c` |
| #12 | Session starts on its own, with the Discussion Phase | `dc35b53` |
| #13 | Voting Phase, two Rounds and the Result | `d8a410b` |
| #16 | Dropouts, Incomplete Sessions and expiry | `0389ecf` |
| #14 | AI Agents in mock mode, Blind Condition check and reveal setting | `cd50dcb` |
| #15 | Real LLM for AI Agents | `d0202c7` |
| #17 | Docs and test checklist (this file, README, ARCHITECTURE.md, TESTING.md) | branch `ticket-17` |

Read them with `gh issue view <n> --repo joeytomoyama/max-planck-project`. Every
commit made by an agent ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Not exported

The orchestrator and subagent transcripts of stage 3 are not exported into the repo.
The issues above, the commits and their messages are the record of what each agent was
asked to do and what it did.

## Stage 4: Ticket #19 and README (Nov 23, 2026)

- **Tool:** Claude Code CLI in a terminal on Linux, with the user's skills `implement`
  (ticket workflow), `tdd` (red-green against black-box checks) and `code-review`
  (Standards and Spec subagents). The Playwright MCP server was added mid-session
  (`claude mcp add playwright -- npx @playwright/mcp@latest --browser chromium`).
  Rootless Podman Compose ran the test stacks; `gh` read the issue.
- **Model:** Claude Opus 5.5 (`claude-opus-5-5`) for the session and both review subagents.
- **Full transcript** (every user prompt verbatim, every reply, tool calls summarised):
  [`ai-prompts/2026-11-23-claude-code-ticket-19.md`](ai-prompts/2026-11-23-claude-code-ticket-19.md).

What happened, in order of the user's prompts:

1. `/implement #19`: Humans no longer see "n of m joined" (it gave away the Condition).
   `POST /api/sessions` returns a secret Researcher token; a token-guarded
   `GET /api/sessions/{rc}/researcher` feeds the Condition and live count on `/waiting`.
   Black-box pytest checks in `backend/tests` were written red-first against the old
   code. The code review found the public `GET /api/sessions/{rc}` still listed the
   waiting Humans' Player Labels (another way to count them) and an unguarded
   `POST /start`; both were fixed test-first. Commits `455566d`, `94da7e0`.
2. "did you check it?": Claude listed what was and wasn't verified, including that the
   browser check used a Python Playwright script because Playwright MCP wasn't connected.
3. Setting up Playwright MCP, then "ok run the playwright tests now": the ticket's
   check was redone with Playwright MCP (Researcher 0 → 1 → 2 of 3 → started; Human
   tabs never see a count or receive one). Commit `26512ac`.
4. "how would i now integrate a real llm": explained the existing OpenAI-compatible
   client (ticket #15) and the local Ollama setup; then the README was rewritten to
   include it and describe the repo, and this stage was added to the log.

