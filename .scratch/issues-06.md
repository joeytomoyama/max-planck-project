### What to build

Create YAML-based configuration file for switching between experimental conditions without code changes.

### Blocked by

- Issue 1 (Project Scaffolding)

### Acceptance Criteria

- [ ] config.yml location in project root or /config/
- [ ] Fields: participant_types (list like [human, human, ai]), session_timeout_minutes, round_duration_seconds, llm_api_key (optional)
- [ ] Example configs for all 3 scenarios (3H / 2H+1AI / 1H+2AI) in repo README
- [ ] Backend reads config at startup or via /api/sessions/config endpoint
- [ ] Validate YAML on load; fail startup with clear error if invalid
