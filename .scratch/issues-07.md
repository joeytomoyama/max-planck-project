### What to build

Implement LLM-based conversation generation for AI participants, with prompt caching and reproducibility options.

### Blocked by

- Issue 1 (Project Scaffolding)
- Issue 6 (Configuration File)

### Acceptance Criteria

- [ ] AI participant service reads config.yml for prompt templates and model endpoint
- [ ] On chat message: AI responds within 2-3 seconds using LLM API or mock if disabled
- [ ] Voting behavior: AI votes based on simple strategy (e.g., "vote first majority" or random)
- [ ] Response caching per participant ID + session to ensure consistency
- [ ] Mock mode toggle in config for deterministic demo runs
- [ ] All prompts and models logged in ai_prompts.md with exact parameters
