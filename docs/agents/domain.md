# Domain Model - Max Planck Project

## Glossary (from GLOSSARY.md at repo root)

### Core Concepts

**Session**: A single experiment instance identified by a random room code. Contains participants, rounds, and votes. Status transitions: `waiting` → `active` → `completed`.

**Participant**: An entity in a session, either human or AI agent. Identified by sequential ID (Player A, Player B, etc.) within its session. Stores join time and last activity.

**Round**: A discrete discussion period (~1 minute) with associated chat history and voting results. Auto-numbered per session.

**Vote**: A participant's selection of a target participant to become Decision Maker. Blind voting (participants don't see others' votes until results revealed).

### Participant Types

- **Human**: Real user connecting via web browser
- **AI**: Synthetic participant powered by LLM, following configured prompts and behavior patterns

### Configuration

**Participant Configuration**: Defined in `config.yml`. Groups of human/ai counts:
- `3 Humans`: Baseline human-only interaction
- `2H + 1 AI`: Mixed group with one AI agent  
- `1H + 2 AI`: Majority AI agents

## Database Model (PostgreSQL)

### Core Tables

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| sessions | id, room_code, status | Session lifecycle management |
| participants | session_id, id, name, type | Participant registry per session |
| rounds | session_id, round_number, vote_results | Discussion phases and votes |
| votes | session_id, participant_id, target_participant | Individual vote records |

### Relationships

- sessions.one() → participants.many()
- sessions.one() → rounds.many()
- sessions.one() → votes.many()
- rounds.one() → votes.many()

## State Transitions

```
Session: waiting → active (start button) → completed (all rounds done)
Participant: joined → inactive (timeout or explicit leave)
Round: pending → discussion → voting → results
```

## AI Behavior Model

When `MOCK_LLM=true`, responses are deterministic based on message hash. When false, real LLM calls generate natural conversation following system prompts and context awareness.
