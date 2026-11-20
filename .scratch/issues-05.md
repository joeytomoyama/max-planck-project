### What to build

Build the /room/:sessionId route with discussion rounds, chat interface, and voting UI.

### Blocked by

- Issue 1 (Project Scaffolding)
- Issue 3 (Backend API with WebSocket)
- Issue 4 (React Waiting Room)

### Acceptance Criteria

- [ ] Route /room/:sessionId displays chat history and active round timer (~1 min)
- [ ] Chat input with send button; messages appear in reverse chronological order
- [ ] Round 1 discussion -> "Ready to vote" button appears after time expires
- [ ] Voting UI: radio buttons for each participant (A/B/C) + submit
- [ ] On vote: show confirmation toast ("Your vote recorded") but not others' votes
- [ ] After all votes: display results with selected Decision Maker highlighted
- [ ] Round 2 discussion can occur if voting doesn't complete round 1
