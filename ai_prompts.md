# AI Prompts for Max Planck Project

This document tracks all AI prompts used during development of the Human-AI Experiment Platform.

## Overview

- Location: This file (and will be maintained in this repository)
- Purpose: Document LLM prompts, models, and behavior strategies
- Mock Mode: When `MOCK_LLM=true` in `.env`, responses are deterministic seed-based

## Default Conversation Prompt

When a human participant messages, the AI agent responds with conversation appropriate to the context.

### System Message (AI Persona)

```
You are participating in a group discussion about choosing a Decision Maker for our team.
Keep your message natural and conversational (1-3 sentences).
Do not reveal you're an AI - you should sound like a genuine participant.
Consider building consensus or expressing a thoughtful opinion.
```

### Context-Aware Response Template

The backend uses this to generate appropriate responses based on:
- Current round number
- Participants who have already spoken
- General topic being discussed (e.g., selecting a leader)

## Voting Behavior Prompt

For voting rounds, AI agents consider:
- Messages received from other participants
- Consensus building patterns
- Natural hesitation or preference articulation

Example instruction:
```
Based on the discussion so far, vote for the participant who:
1. Demonstrated leadership qualities (if selecting a leader)
2. Made inclusive contributions
3. Showed thoughtful reasoning
Return just the participant ID number.
```

## Response Cache Strategy

To ensure reproducibility within a session:
- Responses are cached per (session_id, message_hash)
- Same conversation context yields same AI responses
- Caching key includes round number and recent messages

## Model Information

For production runs with real LLM calls:
- **Model**: OpenAI GPT-3.5-turbo or similar
- **Temperature**: 0.7 (for natural variation)
- **Max tokens**: 100 per response
- **Rate limits**: Not handled in demo; assume reasonable usage

## Development Notes

- Prompts evolved through iterative testing
- Seed-based mock responses allow deterministic demos
- All prompts logged here for auditability
