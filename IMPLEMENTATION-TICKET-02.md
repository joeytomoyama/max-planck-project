# Ticket #02 Implementation Summary: Database Schema & Seed Data

## Overview

This document summarizes the implementation of the database schema and seed data for the Max Planck Project experiment platform.

## Acceptance Criteria Completed

### ✅ sessions table with proper columns

- **id**: SERIAL PRIMARY KEY (auto-increment)
- **oom_code**: VARCHAR(64) UNIQUE NOT NULL (unique session identifier, e.g., "oom-abc123")
- **status**: VARCHAR(20) DEFAULT 'waiting' ('waiting', 'active', 'completed', 'expired')
- **created_at**: TIMESTAMP DEFAULT NOW()
- **expires_at**: TIMESTAMP (session timeout)

**Location**: `backend/src/main.py` and `backend/migrations/001_initial_schema.sql`

### ✅ participants table with proper columns

- **session_id**: INTEGER REFERENCES sessions(id) ON DELETE CASCADE
- **id**: VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY (e.g., "Player A", "A1") - replaced auto-increment serial for simpler WebSocket management
- **type**: VARCHAR(10) CHECK IN ('human', 'ai') - enum constraint enforced
- **joined_at**: TIMESTAMP DEFAULT NOW()
- **last_activity**: TIMESTAMP DEFAULT NOW() (updates on chat/vote events)

**Location**: `backend/src/main.py`, `backend/src/schema.md`

### ✅ rounds table with proper columns

- **session_id**: INTEGER REFERENCES sessions(id) ON DELETE CASCADE
- **round_number**: INTEGER NOT NULL (sequential round number)
- **discussion_start**: TIMESTAMP (nullable, when round discussion began)
- **discussion_end**: TIMESTAMP (nullable, when round discussion ended)
- **vote_results**: JSONB (stores per-round vote counts like `{"A": 2, "B": 1}`)

**Location**: `backend/src/main.py`, `backend/migrations/001_initial_schema.sql`

### ✅ votes table with proper columns

- **id**: SERIAL PRIMARY KEY
- **session_id**: INTEGER REFERENCES sessions(id) ON DELETE CASCADE
- **participant_id**: VARCHAR(20) NOT NULL REFERENCES participants(id) - voter's ID
- **target_participant**: VARCHAR(20) NOT NULL REFERENCES participants(id) - vote target
- **cast_at**: TIMESTAMP DEFAULT NOW()

**Location**: `backend/src/main.py`, `backend/migrations/001_initial_schema.sql`

### ✅ Database migrations documented

Created SQL migration scripts in `backend/migrations/`:
- `001_initial_schema.sql` - Full schema definition with indexes and constraints
- `002_seed_data.sql` - Seed data insertion (uses Python script for simplicity)

Also created documentation in:
- `backend/src/schema.md` - Comprehensive schema documentation
- `backend/init_db.py` - Python initialization script
- `backend/migrations/` folder - SQL migration scripts

### ✅ Seed data script for demo session with 3 participants

Created `backend/src/seed.py` that:
- Creates a demo session with unique ID (e.g., `seed-abc12345`)
- Adds 3 participants: 2 humans ("Player A", "Player B") and 1 AI ("Player C")
- Sets 2-hour expiration by default
- Outputs WebSocket endpoint for connecting

**Usage**:
```bash
python backend/src/seed.py
```

Or automatically create on startup with environment variable:
```bash
export CREATE_SEED=true
docker compose up -d backend
```

### ✅ PostgreSQL container integration

Database schema is initialized automatically on backend container startup via `@app.on_event("startup")` in `backend/src/main.py`.

Also supports manual initialization:
```bash
cd backend
python init_db.py              # Create tables only
python init_db.py --seed       # Create tables + demo session
```

## Files Created/Modified

### Created Files

1. **backend/src/main.py** - Modified to include:
   - Updated database schema with all four tables
   - `init_database()` function for proper initialization
   - WebSocket endpoint handling votes and chat messages
   - Participant management endpoints
   - Seed data creation on startup (if `CREATE_SEED=true`)

2. **backend/src/seed.py** - New file:
   - Demo session creation script
   - Creates 3-participant demo session
   - CLI with `--db` option for custom database URL

3. **backend/migrations/001_initial_schema.sql** - New file:
   - SQL migration script for creating all tables
   - Includes indexes and foreign key constraints

4. **backend/migrations/002_seed_data.sql** - New file:
   - Seed data SQL (commented out, Python preferred)

5. **backend/src/schema.md** - New file:
   - Comprehensive schema documentation
   - Table descriptions, column meanings, and usage examples

6. **backend/init_db.py** - New file:
   - Python initialization script with CLI
   - Supports `--seed` flag for demo session creation

7. **backend/README.md** - New file:
   - Backend module documentation
   - Quick start guide and API reference

8. **backend/tests/test_database.py** - New file:
   - Unit tests for database schema
   - Tests table creation, seed data, constraints

9. **IMPLEMENTATION-TICKET-02.md** - This file

### Modified Files

1. **TESTING.md** - Updated with database testing information and initialization commands

## Database Schema Summary

```sql
-- Sessions table (main entry point)
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    oom_code VARCHAR(64) UNIQUE NOT NULL,      -- e.g., "oom-abc123"
    status VARCHAR(20) DEFAULT 'waiting',       -- waiting|active|completed|expired
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Participants table (linked to sessions)
CREATE TABLE participants (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY, -- e.g., "Player A"
    type VARCHAR(10) CHECK (type IN ('human', 'ai')),
    joined_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW()
);

-- Rounds table (discussion tracking)
CREATE TABLE rounds (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    discussion_start TIMESTAMP,
    discussion_end TIMESTAMP,
    vote_results JSONB  -- e.g., {"A": 2, "B": 1, "C": 0}
);

-- Votes table (individual votes)
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    participant_id VARCHAR(20) NOT NULL REFERENCES participants(id),
    target_participant VARCHAR(20) NOT NULL REFERENCES participants(id),
    cast_at TIMESTAMP DEFAULT NOW()
);
```

## Testing

### Run Unit Tests

```bash
cd backend
python -m pytest tests/test_database.py -v
```

### Create Demo Session Manually

```bash
python backend/src/seed.py
```

Or with custom database:

```bash
python backend/src/seed.py --db "postgresql://user:pass@host/dbname"
```

## Notes on Design Decisions

1. **oom_code vs room_code**: Used `oom_code` per schema, but can be renamed to `room_code` if needed.

2. **participants.id as VARCHAR(20)**: Replaced auto-increment serial with participant name (e.g., "Player A") for simpler WebSocket association and matching frontend display labels.

3. **JSONB for vote_results**: Using JSONB allows flexible storage of per-round results without schema changes.

4. **Automatic initialization on startup**: Ensures database is always in consistent state when backend container starts.

## Next Steps (Optional Enhancements)

1. Add round tracking logic to WebSocket handler to populate `rounds` table
2. Implement session expiration cleanup jobs
3. Add more comprehensive tests for API endpoints
4. Consider adding view/helper tables for analytics queries

---

**Implementation Date**: Fri Nov 20 2026  
**Ticket Reference**: [02] Database Schema & Seed Data  
**Status**: ✅ Complete - All acceptance criteria met
