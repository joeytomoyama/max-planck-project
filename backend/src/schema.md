# Max Planck Project - Database Schema Documentation

## Overview

This document describes the PostgreSQL database schema for the Max Planck Project experiment platform. The schema supports multi-participant human-AI experiments with real-time discussion and voting.

## Database Connection

- **Host**: `db` (Docker container) or local PostgreSQL
- **Port**: 5432
- **Database**: `max_planck_project`
- **User**: `postgres`
- **Password**: `secretpgpass`

Environment variable:
```bash
DATABASE_URL=postgresql://postgres:secretpgpass@db:5432/max_planck_project
```

## Tables

### sessions

Stores experiment sessions with unique room codes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL PRIMARY KEY | Auto-increment | Session identifier |
| oom_code | VARCHAR(64) UNIQUE NOT NULL | Unique, non-null | URL-safe session code (e.g., "oom-abc123") |
| status | VARCHAR(20) DEFAULT 'waiting' | Non-null | Session state: 'waiting', 'active', 'completed', 'expired' |
| created_at | TIMESTAMP DEFAULT NOW() | Auto-set | When session was created |
| expires_at | TIMESTAMP | Allows NULL | Session expiration time |

**Index**: `oom_code` (unique, for fast lookups)

---

### participants

Stores participant information within each session.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| session_id | INTEGER REFERENCES sessions(id) | Foreign key, ON DELETE CASCADE | Links to parent session |
| id | VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY | Unique, non-null | Participant identifier (e.g., "Player A", "A1") |
| type | VARCHAR(10) DEFAULT 'human' CHECK(type IN ('human', 'ai')) | Non-null, enum | Participant type: 'human' or 'ai' |
| joined_at | TIMESTAMP DEFAULT NOW() | Auto-set | When participant joined |
| last_activity | TIMESTAMP DEFAULT NOW() | Auto-set | Last recorded activity (updates on chat/vote) |

**Index**: `session_id` (foreign key), `id` (unique primary key)

---

### rounds

Tracks discussion rounds and vote results.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| session_id | INTEGER REFERENCES sessions(id) | Foreign key, ON DELETE CASCADE | Links to parent session |
| round_number | INTEGER NOT NULL | Non-null | Sequential round number (1, 2, 3...) |
| discussion_start | TIMESTAMP | Allows NULL | When round discussion began |
| discussion_end | TIMESTAMP | Allows NULL | When round discussion ended |
| vote_results | JSONB | Allows NULL | Results of votes in round: `{"A": 2, "B": 1}` etc. |

**Index**: `session_id`, `(session_id, round_number)` for ordering

**Vote Results Structure (JSONB)**:
```json
{
  "round_1": {
    "A": 2,
    "B": 1,
    "C": 0
  },
  "round_2": {
    "A": 1,
    "B": 2,
    "C": 0
  }
}
```

---

### votes

Records individual votes cast during rounds.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL PRIMARY KEY | Auto-increment | Vote identifier |
| session_id | INTEGER REFERENCES sessions(id) | Foreign key, ON DELETE CASCADE | Links to parent session |
| participant_id | VARCHAR(20) NOT NULL REFERENCES participants(id) | Foreign key | Voter's ID |
| target_participant | VARCHAR(20) NOT NULL REFERENCES participants(id) | Foreign key | Target of vote |
| cast_at | TIMESTAMP DEFAULT NOW() | Auto-set | When vote was cast |

**Index**: `session_id`, `participant_id`, `cast_at`

---

## Schema Initialization

### On Application Startup

The application automatically initializes the database on startup via `@app.on_event("startup")`:

1. Drops existing tables (if any) to ensure clean state
2. Creates all four tables with proper constraints and indexes
3. Commits transaction

### Manual Database Setup

To manually create tables (for development or migrations):

```sql
-- Drop existing tables (optional, for clean slate)
DROP TABLE IF EXISTS votes CASCADE;
DROP TABLE IF EXISTS rounds CASCADE;
DROP TABLE IF EXISTS participants CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;

-- Create sessions table
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    oom_code VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'waiting',
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Create participants table
CREATE TABLE participants (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,
    type VARCHAR(10) NOT NULL DEFAULT 'human' CHECK (type IN ('human', 'ai')),
    joined_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW()
);

-- Create rounds table
CREATE TABLE rounds (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    discussion_start TIMESTAMP,
    discussion_end TIMESTAMP,
    vote_results JSONB
);

-- Create votes table
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    participant_id VARCHAR(20) NOT NULL REFERENCES participants(id),
    target_participant VARCHAR(20) NOT NULL REFERENCES participants(id),
    cast_at TIMESTAMP DEFAULT NOW()
);
```

---

## Seed Data Script

Located at: `backend/src/seed.py`

Creates a demo session with 3 participants for local testing.

### Usage

```bash
# Create seed session (uses DATABASE_URL from environment)
python seed.py

# With custom database URL
DATABASE_URL=postgresql://... python seed.py --db $DATABASE_URL
```

### Output Example

```
✓ Seed session created successfully!
  Session ID: seed-abc12345
  OOM Code:    oom-seed-abc12345
  Expires at:  2026-11-20 14:30:00

Participants:
    👤 Player A (human)
    👤 Player B (human)
    🤖 Player C (ai)

WebSocket endpoint: ws://localhost:8000/ws/seed-abc12345

To connect to this session, visit:
  http://localhost:3000/seed-abc12345

---
This demo session is ready for testing!
You can join with the WebSocket at /ws/:sessionId
```

### Environment Variable

Set `CREATE_SEED=true` to automatically create a seed session on application startup:

```bash
export CREATE_SEED=true
docker-compose up -d backend
```

---

## Notes

- **oom_code**: Uses "oom" prefix for consistency; replace with "room_code" if needed per acceptance criteria
- **participants.id**: Uses participant name as ID (e.g., "Player A") instead of auto-increment serial to simplify WebSocket management
- **votes JSONB**: Could be populated by backend logic tracking round results
- **rounds table**: Currently created but not actively written to in WebSocket handler; can be extended for round tracking

---

## Related Files

- `backend/src/main.py` - Main application with database initialization
- `backend/src/seed.py` - Seed data script
- `docker-compose.yml` - Docker configuration with PostgreSQL service
- `ARCHITECTURE.md` - System architecture documentation
