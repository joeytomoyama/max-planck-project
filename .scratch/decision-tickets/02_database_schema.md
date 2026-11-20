# Ticket 02: Database Schema & Seed Data

## Description
Define and create PostgreSQL tables with proper constraints, indexes, and seed data for initial session creation.

## Blocking Edges
- 01_project_scaffolding: Docker infrastructure must be in place to connect to DB

## Unblocks
- 03_backend_api: API needs database schema to persist state
- End-to-end tests requiring sessions

## User Stories Covered
2. As a human participant, I want to wait in the lobby until all slots are filled...
6. As a system, I want to auto-assign round numbers and track discussion time...
8. As a researcher, I want the app to display final results and the selected Decision Maker...

## Acceptance Criteria
- [ ] `sessions` table: `id`, `room_code` (unique), `created_at`, `expires_at`, `status`
- [ ] `participants` table: `session_id`, `id`, `type` (enum: human/ai), `joined_at`, `last_activity`
- [ ] `rounds` table: `session_id`, `round_number`, `discussion_start`, `discussion_end`, `vote_results` (JSONB)
- [ ] `votes` table: `session_id`, `participant_id`, `target_participant`, `cast_at`
- [ ] Database migrations documented (or use raw SQL since PostgreSQL container)
- [ ] Seed data script to create demo session with 3 participants for local testing

## Implementation Notes
Use SQLAlchemy ORM with Alembic for migrations, or raw SQL if staying minimal. Keep migrations simple—PostgreSQL is already containerized via docker-compose.
