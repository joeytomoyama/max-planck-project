# Architecture Documentation

## Overview

Max Planck Project is a Docker Compose-based monorepo hosting:
- **Frontend**: React SPA served statically from the backend container
- **Backend**: FastAPI Python server with WebSocket support
- **Database**: PostgreSQL with persistent storage

## Directory Structure

```
max-planck-project/
├── docker-compose.yml          # Orchestration entry point
├── .env.example                # Environment variables template
├── backend/                    # FastAPI backend
│   ├── Dockerfile             # Python + static files build
│   ├── src/main.py            # API endpoints, WebSocket handler
│   └── requirements.txt       # Python dependencies
├── frontend/                   # React SPA
│   ├── Dockerfile             # Multi-stage: build + serve
│   ├── public/index.html      # React entry point
│   └── src/                    # React components
├── config/                     # YAML configuration files
├── docs/                       # Agent documentation
└── docker/                     # CI/test scripts
```

## Key Design Decisions

### 1. Frontend Served from Backend Container

**Decision**: Copy built React static files into backend image.

**Rationale**: 
- Simpler than separate nginx/static container
- Single container entry point in docker-compose.yml
- Avoids reverse proxy complexity

**Trade-off**: Build step must complete before container starts.

### 2. Session-Based Isolation (No JWT)

**Decision**: Random room codes + PostgreSQL session tracking.

**Rationale**: 
- Controlled research environment
- Simple session ID-based isolation suffices
- No need for full auth infrastructure

**Trade-off**: Less suitable for open/public deployments.

### 3. WebSocket Over HTTP/WS

**Decision**: Single `ws://` endpoint per session (`/ws/{session_id}`).

**Rationale**: 
- Bidirectional real-time updates
- Efficient for chat + voting events
- No polling needed

**Trade-off**: Requires WebSocket server (handled by uvicorn).

### 4. Mock LLM Responses with Seed Option

**Decision**: Toggle mock mode via environment variable.

**Rationale**: 
- Deterministic testing in development
- Real API calls in production
- Easy switch for demo purposes

**Trade-off**: Production should disable mock mode and handle rate limits.

## Database Schema

### sessions
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| room_code | VARCHAR(64) | URL-safe session identifier |
| status | VARCHAR(20) | waiting / active / completed |
| created_at | TIMESTAMP | Session creation time |
| expires_at | TIMESTAMP | When session times out |

### participants
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Participant identifier in session |
| session_id | INTEGER | FK to sessions.id |
| name | VARCHAR(32) | "Player A", etc. or AI persona |
| type | VARCHAR(10) | human / ai |

### rounds, votes
- Track discussion progression and voting results
- Vote_results stored as JSONB for flexible schema

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions` | List recent sessions |
| GET | `/api/sessions/:id` | Get session details |
| GET | `/api/sessions/:id/start` | Activate waiting session |
| GET | `/api/sessions/:id/config` | Get participants + config |
| POST | `/api/rooms/:code` | Create new room |

### WebSocket `/ws/{session_id}`
- Accepts chat messages as text
- Sends broadcast updates to all clients
- Closes on disconnect or session expiry

## Docker Compose Services

```yaml
db:           # PostgreSQL 15 Alpine
backend:      # FastAPI Python app
frontend:     # React SPA (served via backend static)
```

All services share a single docker-compose.yml for simplicity.

## Build Pipeline

```bash
# Local development setup
docker compose up --build

# Production build (optimizes images)
DOCKER_BUILDKIT=1 docker compose build
docker compose up -d

# Test CI script
./docker/test-ci.sh
```

## Security Considerations

- PostgreSQL uses volume-mounted persistent storage
- Environment variables for secrets (.env file recommended)
- No JWT/complex auth needed for research context
- Simple input sanitization for chat messages

## Out of Scope (Per Specification)

- Full unit/integration test suite with CI pipeline
- Production-grade security beyond basic sanitization
- Multi-user collaboration features
- Analytics dashboard
