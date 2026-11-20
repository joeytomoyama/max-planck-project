# Ticket 04: React Waiting Room (Lobby)

## Description
Build the `/waiting` route with room code display, join button, and waiting logic until session fills.

## Blocking Edges
- 01_project_scaffolding: React app scaffold exists
- 03_backend_api: API contract for sessions must be defined

## Unblocks
- 05_rounds_and_voting: Waiting room → rounds transition depends on this

## User Stories Covered
1. As a researcher, I want to start a new experiment session via the waiting room...
2. As a human participant, I want to wait in the lobby until all slots are filled...

## Acceptance Criteria
- [ ] Route `/waiting` displays "Waiting for others to join..." with animated loader
- [ ] Display generated room code (random 4-6 char string) as copyable link
- [ ] Show participant count: X/3 joined (blocks until all 3 are present)
- [ ] Click "Join Session" connects WebSocket and polls API for slot availability
- [ ] On session start, redirect to `/room/:sessionId` automatically
- [ ] Handle timeout scenario with retry prompt

## Implementation Notes
Poll API every 2 seconds for new participants. Use React Context or Zustand for WebSocket state if needed. Keep UI minimal—no need for complex animations beyond basic loader.
