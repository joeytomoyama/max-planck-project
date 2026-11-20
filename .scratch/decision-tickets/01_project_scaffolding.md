# Ticket 01: Project Scaffolding & Docker Configuration

## Description
Set up the monorepo structure with Docker Compose, basic project files, and CI-ready environment. This is the foundation ticket that enables all other tickets.

## Blocking Edges
- None (this is a root-level task)

## Unblocks
- 02_database_schema: Needs docker-compose to spin up PostgreSQL
- 03_backend_api: Depends on Docker scaffold
- 04_waiting_room_ui: Needs backend routes to be defined
- 05_rounds_and_voting: Depends on database and API
- 06_ai_agent_integration: Requires all infrastructure

## User Stories Covered
1. As a researcher, I want to start a new experiment session via the waiting room...
2. As a participant, I want to wait in the lobby until all slots are filled...
8. As a system, I want AI agents to generate natural conversation responses...
10. As a researcher, I want to use Docker Compose to start the entire application...

## Acceptance Criteria
- [ ] `docker-compose.yml` created with backend, frontend, PostgreSQL services
- [ ] Project root structure: `/backend`, `/frontend`, `/config`, `/docker`, `README.md`
- [ ] `.env.example` file with documented variables
- [ ] Basic Docker build succeeds without errors
- [ ] Backend container starts and connects to PostgreSQL
- [ ] Frontend React app can be built in production mode

## Implementation Notes
Use FastAPI for backend, Create React App or Vite for frontend. Keep Dockerfiles minimal—build backend with dependencies, frontend as static files copy after build.
