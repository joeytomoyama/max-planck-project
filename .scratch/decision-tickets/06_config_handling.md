# Ticket 06: Configuration File (`config.yml`)

## Description
Create YAML-based configuration file for switching between experimental conditions without code changes.

## Blocking Edges
- 01_project_scaffolding: Project root exists

## Unblocks
- 07_ai_agent_integration: AI behavior depends on config
- End-to-end tests for all three participant type scenarios

## User Stories Covered
5. As a researcher, I want to configure participant types (3 humans / 2 humans + 1 AI / 1 human + 2 AIs) via `config.yml`...

## Acceptance Criteria
- [ ] `config.yml` location in project root (or `/config/`)
- [ ] Fields: `participant_types` (list like `[human, human, ai]`), `session_timeout_minutes`, `round_duration_seconds`, `llm_api_key` (optional)
- [ ] Example configs for all 3 scenarios (3H / 2H+1AI / 1H+2AI) in repo README
- [ ] Backend reads config at startup or via `/api/sessions/config` endpoint
- [ ] Validate YAML on load; fail startup with clear error if invalid

## Implementation Notes
Load config once at app startup. For tests, allow overriding via env vars without modifying `config.yml`. Store API keys in `.env`, read from environment, never commit secrets to repo.
