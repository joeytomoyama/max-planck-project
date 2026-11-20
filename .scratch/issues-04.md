### What to build

Build the /waiting route with room code display, join button, and waiting logic until session fills.

### Blocked by

- Issue 1 (Project Scaffolding)
- Issue 3 (Backend API with WebSocket)

### Acceptance Criteria

- [ ] Route /waiting displays "Waiting for others to join..." with animated loader
- [ ] Display generated room code as copyable link
- [ ] Show participant count: X/3 joined (blocks until all 3 present)
- [ ] Click "Join Session" connects WebSocket and polls API for slot availability
- [ ] On session start, redirect to /room/:sessionId automatically
- [ ] Handle timeout scenario with retry prompt
