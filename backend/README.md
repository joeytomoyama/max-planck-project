# Max Planck Project - Backend Module

## Overview

FastAPI backend for the Multi-Participant Human-AI Experiment Platform. Handles sessions, WebSocket communication, and REST endpoints for real-time chat and voting.

## Quick Start

### Using Docker Compose (Recommended)

```bash
docker compose up --build -d
```

This starts:
- PostgreSQL database (`db`)
- Backend API (`backend`, port 8000)
- Frontend SPA (`frontend`, port 3000)

### Environment Variables

```bash
# Database connection
DATABASE_URL=postgresql://postgres:secretpgpass@db:5432/max_planck_project

# Optional: Create seed session on startup
export CREATE_SEED=true

# Mock LLM for deterministic testing
MOCK_LLM=true
```

## Database Schema

See [backend/src/schema.md](src/schema.md) for detailed documentation.

### Tables

- `sessions` - Experiment sessions with unique room codes
- `participants` - Participants with type (human/ai) and activity tracking
- `rounds` - Discussion rounds with vote results (JSONB)
- `votes` - Individual votes cast during rounds

### Initialization

**Option 1: Automatic (recommended)**

Database tables are created automatically on backend container startup.

```bash
docker compose up -d backend
```

**Option 2: Manual initialization**

Initialize database directly from the backend directory:

```bash
cd backend
python init_db.py                    # Create tables only
python init_db.py --seed             # Create tables + demo session
```

Or use Python REPL for custom setup:

```bash
python -c "import sys; sys.path.insert(0, 'src'); from main import init_database; init_database()"
```

**Option 3: SQL script**

```bash
psql -h localhost -U postgres -d max_planck_project -f migrations/001_initial_schema.sql
```

## API Endpoints

### Sessions

- `GET /api/sessions` - List recent sessions
- `GET /api/sessions/{session_id}` - Get session details
- `GET /api/sessions/{session_id}/start` - Start a waiting session
- `POST /api/sessions/{session_id}/participant` - Add participant

### Rooms (Legacy)

The `rooms` table and `/api/rooms/{room_code}` endpoint are deprecated in favor of sessions with `oom_code`.

## Seed Data

Create a demo session for local testing:

```bash
python backend/src/seed.py
```

Or set environment variable to auto-create:

```bash
export CREATE_SEED=true
docker compose up -d backend
```

This creates a session with 3 participants (2 humans, 1 AI) at `session_id` like `seed-abc12345`.

## Testing

### Unit Tests

```bash
cd backend
python -m pytest tests/test_database.py -v
```

### Integration Tests

Run through Playwright MCP for end-to-end testing of:
- Waiting room flow
- Discussion rounds
- Voting mechanics
- Session expiration

See [TESTING.md](../TESTING.md) for details.

## File Structure

```
backend/
├── README.md                    # This file
├── Dockerfile                   # Backend container build
├── requirements.txt            # Python dependencies
├── tests/
│   ├── __init__.py
│   └── test_database.py        # Database unit tests
├── static/                     # React build output (served via StaticFiles)
└── src/
    ├── __init__.py
    ├── main.py                 # FastAPI application
    ├── seed.py                 # Seed data script
    └── schema.md               # Schema documentation
```

## Dependencies

- FastAPI
- psycopg2-binary (PostgreSQL driver)
- SQLAlchemy ORM
- uvicorn (ASGI server)

Install with:

```bash
pip install -r requirements.txt
```

## Architecture Notes

- **Sync database operations**: Uses synchronous `psycopg2` for simplicity in Docker environment
- **WebSocket connections**: Thread-local storage manages active connections per session
- **Session isolation**: Simple room code-based; no JWT tokens needed for controlled research context

## Related Documentation

- [SPEC.md](../SPEC.md) - Full project specification
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [docker-compose.yml](../docker-compose.yml) - Container configuration
