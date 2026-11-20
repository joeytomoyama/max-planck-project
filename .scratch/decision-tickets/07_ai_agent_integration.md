# Ticket 07: AI Agent Behavior & Prompt Integration

## Description
Implement LLM-based conversation generation for AI participants, with prompt caching and reproducibility options.

## Blocking Edges
- 01_project_scaffolding: Project exists
- 06_config_handling: Config file with AI settings must exist

## Unblocks
- End-to-end testing of AI vs human scenarios

## User Stories Covered
5. As a researcher, I want to configure participant types...
9. As a system, I want AI agents to generate natural conversation responses using LLM API calls...
12. As a reviewer, I want an AI Usage Log documenting all prompts used during development...

## Acceptance Criteria
- [ ] AI participant service reads `config.yml` for prompt templates and model endpoint
- [ ] On chat message: AI responds within 2-3 seconds using LLM API (or mock if disabled)
- [ ] Voting behavior: AI votes based on simple strategy (e.g., "vote first majority" or random)
- [ ] Response caching per participant ID + session to ensure consistency
- [ ] Mock mode toggle in config for deterministic demo runs
- [ ] All prompts and models logged in `./ai_prompts.md` with exact parameters

## Implementation Notes
Use a simple prompt template like: "You are {name}, discuss the topic and suggest whether you support Player A, B, or C. Keep it to 2-3 sentences." Cache responses per `{session_id|participant_type|prompt_template}` to avoid duplicate calls. For demo, use mock that pre-generates responses for common inputs.
