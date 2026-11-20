# Ticket 03: Backend API with WebSocket Support

## Description
Build FastAPI backend with REST endpoints for session management and WebSocket endpoint for real-time chat/voting.

## Blocking Edges
- 01_project_scaffolding: Docker infrastructure
- 02_database_schema: Tables must exist

## Unblocks
- 04_waiting_room_ui: Frontend needs API contract
- 05_rounds_and_voting: Real-time updates depend on WebSocket

## User Stories Covered
2. As a human participant, I want to wait in the lobby until all slots are filled...
7. As a participant, I want to see and type messages in real-time during discussion rounds...
8. As a system, I want AI agents to generate natural conversation responses...

## Acceptance Criteria
- [ ] POST `/api/sessions` – create new session
- [ ] GET `/api/sessions/{id}` – get session details (participant list, current round)
- [ ] POST `/api/sessions/{id}/start` – transition from waiting to active
- [ ] WebSocket `/ws/{session_id}` – bidirectional chat + vote events
- [ ] POST `/api/sessions/{id}/votes` – cast vote without leaking others' choices
- [ ] Error handling: return 405 for closed sessions, proper status messages
- [ ] Rate limiting considerations noted in docs

## Implementation Notes
Use FastAPI `Websocket` with a simple event loop. Messages: `{type: "chat", text: "..."}` and `{type: "vote", target: "Player A"}`. Push voting results to all participants except voter immediately, then reveal after round ends.
