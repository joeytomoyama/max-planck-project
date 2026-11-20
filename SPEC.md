# Technical Assessment: Multi-Participant Human-AI Experiment Platform – Specification

## Problem Statement

The Center for Humans and Machines at MPIB builds real-time experimental platforms to study human-AI interaction. Researchers need a lightweight web application to simulate 3-participant group decision-making experiments where participants (human or AI agents) cannot know whether others are humans or AIs during the session. The platform must support configurable participant types, real-time discussion and voting across rounds, and display final results—all within a simple Docker setup.

## Solution

A monorepo web application with:
- **Frontend**: React SPA serving routes for waiting room (`/waiting`) and experiment rooms (`/room/:sessionId`)
- **Backend**: FastAPI Python backend providing WebSocket channels for real-time chat/voting, REST endpoints for session state management
- **Database**: PostgreSQL storing sessions, participants, rounds, and votes
- **Containerization**: Docker Compose spinning up frontend, backend, and PostgreSQL in a single command
- **AI Agent Behavior**: LLM-powered responses with configurable prompts stored in `config.yml`

## User Stories

1. As a researcher, I want to start a new experiment session via the waiting room, so that participants can join anonymously without knowing their roles.
2. As a human participant, I want to wait in the lobby until all slots are filled, so that my experience is representative of actual group dynamics.
3. As a participant (human or AI), I want to see and type messages in real-time during discussion rounds, so that we can collaborate on selecting a Decision Maker.
4. As a participant, I want to cast a vote for one of the three members after each round, so that the group decision is recorded fairly.
5. As a researcher, I want to configure participant types (3 humans / 2 humans + 1 AI / 1 human + 2 AIs) via `config.yml`, so that I can run all experimental conditions without code changes.
6. As a system, I want to auto-assign round numbers and track discussion time (~1 minute per round), so that experiment timing is controlled.
7. As a participant, I want to see intermediate feedback (e.g., "Your vote has been recorded") without learning others' votes, so that voting remains blind until results are published.
8. As a researcher, I want the app to display final results and the selected Decision Maker after all rounds conclude, so that experiment outcomes are clearly reported.
9. As a system, I want AI agents to generate natural conversation responses using LLM API calls, so that they blend indistinguishably from human participants.
10. As a researcher, I want to use Docker Compose to start the entire application with a single command, so that deployment is frictionless on any machine.
11. As a researcher, I want clear documentation explaining how to run the project and switch configurations, so that the app is easy to onboard others to.
12. As a reviewer, I want an AI Usage Log documenting all prompts used during development, so that my AI-assisted work is transparent.

## Implementation Decisions

### Frontend Architecture
- Build a single-page React application with client-side routing using React Router v6+
- Define two main routes: `/waiting` (lobby) and `/room/:sessionId` (experiment room)
- Use nested components that change based on session state: `waiting → discussion round 1 → vote → results`
- Store session state in the backend; frontend only maintains UI state

### Backend Communication Model
- Use FastAPI with WebSocket support (`websockets` or `libwebsocket`) for bidirectional real-time updates
- WebSocket endpoint `/ws/{session_id}` handles both chat messages and voting events
- REST endpoints: `/api/sessions`, `/api/sessions/{id}/start`, `/api/sessions/{id}/config`
- No polling required—WebSocket pushes keep the UI responsive

### Database Schema (PostgreSQL)
- **sessions** table: `id`, `room_code` (URL-safe), `created_at`, `expires_at`, `status` (waiting → active → completed)
- **participants** table: `session_id`, `id` (assigned on join, e.g., "Player A"), `type` (human/ai), `joined_at`, `last_activity`
- **rounds** table: `session_id`, `round_number`, `discussion_start`, `discussion_end`, `vote_results` (JSONB)
- **votes** table: `session_id`, `participant_id`, `target_participant`, `cast_at`

### Docker Configuration
- Two separate containers: frontend (`frontend`) and backend (`backend`), both in a single `docker-compose.yml`
- PostgreSQL container mounted with persistent volume for data
- Frontend served via FastAPI's StaticFiles after React build is copied into backend image
- No reverse proxy needed—static paths are proxied at runtime in backend config

### AI Agent Behavior
- Configure participant types and LLM prompts in `config.yml`
- Use actual LLM API calls (or mock local server for demo) to generate conversation and voting behavior
- Document prompt strategies in `/ai_prompts.md` with exact model names and parameters used
- Cache responses per participant state to ensure reproducibility within a session

### Security & Session Isolation
- Use simple session ID-based isolation; no JWT tokens needed for controlled research context
- Sessions expire after timeout (e.g., 15 minutes of inactivity)
- Store session state in PostgreSQL with status tracking; ephemeral memory not required
- Room codes are random and URL-safe, preventing session enumeration

### Documentation Strategy
- Write comprehensive inline comments for non-obvious logic
- Create `ARCHITECTURE.md` explaining design choices and trade-offs
- Maintain `/ai_prompts.md` documenting all AI prompts used during development
- Keep README concise with run instructions, configuration switch guide, and key decisions

### Testing Strategy
- Use Playwright MCP for end-to-end tests covering key flows:
  - Waiting room fills up from empty
  - Discussion rounds progress (chat messages appear)
  - Voting works and results display correctly
  - Session timeout expiration behavior
- Create `TESTING.md` with manual verification checklist for flows not covered by automation
- Document skipped test scenarios with reasons (e.g., edge cases like network failure, tie-breaking logic)

## Out of Scope

- Full unit/integration test suite with CI pipeline setup (manual tests suffice per TESTING.md)
- Advanced authentication/authorization beyond session-based isolation
- Complex error handling for network failures or database timeouts
- Detailed logging infrastructure (simple console logs suffice)
- Production-grade security beyond basic input sanitization
- Multi-user collaboration features (single researcher controls experiments)

## Further Notes

### Trade-offs Made Within 4-Hour Limit

1. **React SPA served from backend**: Simpler Dockerfile than separate nginx/static container; avoids reverse proxy complexity. Static files copied into backend image at build time.

2. **Simple session ID isolation over JWT**: Appropriate for controlled research context where room codes are random and sessions expire. Adding full auth would increase code surface area without proportional benefit.

3. **LLM calls without rate limit handling**: For demo purposes, assume reasonable API usage. Production would need queueing/backpressure but not needed for this scope.

4. **Minimal error pages**: Generic React fallback for 500s; custom error pages were cut due to time.

5. **Mock LLM responses with seed option**: Primary code uses real LLM calls, but a mock server can be toggled in config for deterministic demo runs.

### What Was Not Implemented

- Tie-breaking logic when votes are split evenly (arbitrary winner selected)
- Rich chat UI beyond plain text messages (no markdown rendering)
- Session history/archiving features
- Analytics dashboard for researchers

### AI Usage Log Location

All development prompts and models will be documented in: `./ai_prompts.md` (or `.github/ai-prompts/` folder depending on final structure).

---

*This specification was produced after the `/grill-with-docs` session, capturing all design decisions made during the assessment phase.*
