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
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/max_planck_project

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

- `POST /api/sessions` - Create a waiting session (201) with a server-generated
  URL-safe room code and a 15-minute expiry. No request body; response is
  `{"session": {...}}`.
- `GET /api/sessions` - List recent sessions
- `GET /api/sessions/{session_id}` - Get session details, participants, and
  `current_round` (the highest round number recorded so far, or null)
- `POST /api/sessions/{session_id}/start` - Transition a waiting session to active
- `GET /api/sessions/{session_id}/config` - Get session config and participants
- `POST /api/sessions/{session_id}/participant` - Add participant
- `POST /api/sessions/{session_id}/votes` - Cast a blind vote with
  `{"from_participant": "Player A", "target": "Player B"}`. The response only
  acknowledges the vote; it never includes the target, tallies, or other votes.
  Non-waiting starts and votes on closed/expired sessions return 409, unknown
  sessions 404, and invalid targets/self-votes 400.

The legacy `GET .../start` and `POST .../vote` routes are gone.

### WebSocket `/ws/{session_id}`

JSON frames only; the session must be active and unexpired (otherwise the
socket is closed with code 4001).

Client → server:
- `{"type": "chat", "text": "hello"}`
- `{"type": "vote", "target": "Player B"}`
- `{"type": "ping"}`

Server → client:
- `{"type": "chat", "text": "hello"}` (broadcast to everyone in the session)
- `{"type": "vote_ack", "message": "Your vote has been recorded"}` (voter only)
- `{"type": "vote_notice", "message": "A vote was cast"}` (everyone except the
  voter — anonymous, so the target stays blind)
- `{"type": "error", "message": "..."}` (invalid frame, invalid vote, closed session)
- `{"type": "pong"}`

Votes are validated and recorded before any frame is sent; a failed vote is
never announced to peers. The old `chat:`/`vote:` text frames are no longer
accepted, so the current frontend chat needs the ticket #04 rewrite.

### Rate limiting

There is no per-client rate limiting yet. The research setting has at most
three participants per session and bounded round lengths, so the main risk is
a stuck client flooding events. WebSocket frames are validated before any DB
work, adding a duplicate-vote guard, and the session expiry check bounds how
long a client can keep sending. Add connection/message throttling before any
public or multi-session deployment.

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

Fast unit tests run without a database; DB-schema tests are opt-in integration
tests because they need a live PostgreSQL instance.

```bash
cd backend
python -m pytest tests -v
# with a live database:
RUN_DB_INTEGRATION_TESTS=true python -m pytest tests -v
```

Coverage: `test_api.py` (HTTP surface), `test_votes.py` (blind REST voting),
`test_websocket.py` (JSON-frame channel), `test_database.py` (opt-in schema).

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
│   ├── conftest.py             # Shared fakes and fixtures
│   ├── test_api.py             # HTTP session API tests
│   ├── test_votes.py           # Blind REST voting tests
│   ├── test_websocket.py       # JSON-frame WebSocket tests
│   └── test_database.py        # Opt-in live-DB schema tests
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
