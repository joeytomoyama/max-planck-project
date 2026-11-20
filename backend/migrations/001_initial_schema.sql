-- Migration 001: Initial Schema for Max Planck Project
-- Creates all tables with proper constraints and indexes

-- Drop existing tables if they exist (idempotent for clean migrations)
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

COMMENT ON COLUMN sessions.oom_code IS 'Unique URL-safe session identifier (e.g., "oom-abc123")';

-- Create participants table
CREATE TABLE participants (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,
    type VARCHAR(10) NOT NULL DEFAULT 'human',
    joined_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW()
);

-- Create CHECK constraint for type enum
ALTER TABLE participants 
ADD CONSTRAINT participants_type_check 
CHECK (type IN ('human', 'ai'));

COMMENT ON COLUMN participants.id IS 'Participant identifier (e.g., "Player A", "A1")';
COMMENT ON COLUMN participants.type IS 'Participant role: "human" or "ai"';

-- Create rounds table
CREATE TABLE rounds (
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    discussion_start TIMESTAMP,
    discussion_end TIMESTAMP,
    vote_results JSONB
);

COMMENT ON COLUMN rounds.session_id IS 'Foreign key to sessions table';
COMMENT ON COLUMN rounds.round_number IS 'Sequential round number for this session';
COMMENT ON COLUMN rounds.vote_results IS 'JSONB storing vote counts per participant (e.g., {"A": 2, "B": 1})';

-- Create votes table
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    participant_id VARCHAR(20) NOT NULL,
    target_participant VARCHAR(20) NOT NULL,
    cast_at TIMESTAMP DEFAULT NOW()
);

-- Add foreign key constraints to participants table
ALTER TABLE votes 
ADD CONSTRAINT votes_session_fk 
FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE;

ALTER TABLE votes 
ADD CONSTRAINT votes_participant_fk 
FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE;

ALTER TABLE votes 
ADD CONSTRAINT votes_target_participant_fk 
FOREIGN KEY (target_participant) REFERENCES participants(id) ON DELETE CASCADE;

-- Add indexes for performance
CREATE INDEX idx_sessions_oom_code ON sessions(oom_code);
CREATE INDEX idx_participants_session_id ON participants(session_id);
CREATE INDEX idx_votes_session_id ON votes(session_id);
CREATE INDEX idx_votes_participant_id ON votes(participant_id);
CREATE INDEX idx_votes_target_participant ON votes(target_participant);

-- Create a composite index on votes for querying by session and voter
CREATE INDEX idx_votes_session_participant ON votes(session_id, participant_id);
