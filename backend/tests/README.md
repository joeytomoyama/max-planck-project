# Testing README for Backend Module

## Running Tests

### Prerequisites

PostgreSQL container must be running (via `docker compose up`).

### Unit Tests

Run database schema tests:

```bash
cd backend
python -m pytest tests/test_database.py -v
```

### Test Coverage

Tests cover:
- Table creation and structure validation
- Seed session creation with 3 participants
- Participant type enum constraints
- Foreign key relationships
- Index creation verification

## Manual Testing

Since full integration requires running Docker containers, also verify by:

1. Starting containers: `docker compose up --build -d`
2. Creating seed session: `python src/seed.py`
3. Querying database to verify tables exist:

```bash
psql -h localhost -U postgres -d max_planck_project -c "\dt"
```

Expected output (4 tables):
- public.sessions
- public.participants  
- public.rounds
- public.votes
