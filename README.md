# Max Planck Project: Human-AI Experiment Platform

A multi-participant human-AI experiment platform for studying group decision-making dynamics.

## Quick Start

```bash
docker compose up --build
```

Visit http://localhost:3000/waiting to start a new session.

## Directory Structure

- `/backend` - FastAPI Python backend with WebSocket support
- `/frontend` - React SPA for waiting room and experiment rooms
- `/config` - Configuration files (config.yml, AI prompts)
- `/docker` - Docker-related files
- `/nginx` - Optional Nginx configuration

## Environment Variables

Copy `.env.example` to `.env` and customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | `secretpgpass` | PostgreSQL admin password |
| `POSTGRES_DB` | `max_planck_project` | Database name |
| `BACKEND_PORT` | `8000` | Backend API port |
| `FRONTEND_PORT` | `3000` | Frontend web interface port |

## Configuration Switches

- **Participant types** (3 humans / 2H+1AI / 1H+2AI): Configure in `/config/config.yml`
- **LLM prompts**: Edit `/config/ai_prompts.md` or use mock responses via `MOCK_LLM=true`

## Documentation

- ARCHITECTURE.md - Design decisions and trade-offs
- TESTING.md - Manual test checklist
- docs/agents/domain.md - Domain model and terminology
- ai_prompts.md - All AI prompts used during development
