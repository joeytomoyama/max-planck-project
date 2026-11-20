# AI Usage Log - Max Planck Project

## Overview

This document tracks all AI-assisted development work done on the Max Planck Project. Per specification, this ensures transparency about prompts and models used during implementation of ticket #01.

## Development Session: Nov 20, 2026

### Model Used

- **Provider**: Ollama
- **Model**: qwen3.5:9b (or similar available model)

### Tasks Performed

All scaffolding and setup work for ticket #01 was AI-assisted via the implement skill framework.

#### Files Created with AI Assistance

**Docker & Infrastructure:**
- `docker-compose.yml` - Multi-service orchestration
- `.env.example` - Environment variable documentation
- `backend/Dockerfile` - Python + React build image
- `frontend/Dockerfile` - React build + nginx serve image

**Backend (FastAPI):**
- `backend/requirements.txt` - Dependencies
- `backend/src/main.py` - API endpoints, WebSocket handling, DB schema

**Frontend (React):**
- `frontend/package.json` - Node dependencies
- `frontend/public/index.html` - React entry point
- `frontend/src/index.js` - React root rendering
- `frontend/src/App.js` - Router, WaitingRoom/ExperimentRoom components
- `frontend/src/styles.css` - Basic styling

**Configuration:**
- `config/config.yml` - Participant type configurations
- `ai_prompts.md` - AI prompt documentation (spec requirement)

**Documentation:**
- `README.md` - Project overview and run instructions
- `ARCHITECTURE.md` - Design decisions and trade-offs
- `TESTING.md` - Manual verification checklist

### Prompts Used During Implementation

The following were key prompts (or prompt categories) used:

1. **"Set up Docker Compose with backend, frontend, PostgreSQL"**
   - Produced: `docker-compose.yml`, `.env.example`

2. **"Create FastAPI backend with WebSocket and REST endpoints"**
   - Producing: session management, chat broadcasting, room creation

3. **"Build React SPA with routes for /waiting and /room/:sessionId"**
   - Client-side routing, state management, real-time updates

4. **"Document all AI prompts in ai_prompts.md"**
   - Per spec requirement for transparency

### Models and Parameters

- **Mock Mode**: Enabled by default (`MOCK_LLM=true`)
- **Temperature**: 0.7 for creativity (when enabled)
- **Deterministic Testing**: Seed-based responses for reproducibility

## Future Logging

Additional AI usage will be logged here when:
- New feature tickets are implemented
- Prompt strategies evolve
- Production LLM calls are integrated

---

*This log is maintained per Specification section 12 (AI Usage Log Location).*
