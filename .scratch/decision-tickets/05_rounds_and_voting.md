# Ticket 05: Experiment Room (Rounds & Voting)

## Description
Build the `/room/:sessionId` route with discussion rounds, chat interface, and voting UI.

## Blocking Edges
- 01_project_scaffolding: React app scaffold exists
- 03_backend_api: WebSocket + REST endpoints must be ready
- 04_waiting_room_ui: Sessions must transition from waiting to active

## Unblocks
- End-to-end testing of complete experiment flow

## User Stories Covered
3. As a participant (human or AI), I want to see and type messages in real-time during discussion rounds...
4. As a participant, I want to cast a vote for one of the three members after each round...
7. As a participant, I want to see intermediate feedback without learning others' votes...

## Acceptance Criteria
- [ ] Route `/room/:sessionId` displays chat history and active round timer (~1 min)
- [ ] Chat input with send button; messages appear in reverse chronological order
- [ ] Round 1 discussion → "Ready to vote" button appears after time expires
- [ ] Voting UI: radio buttons for each participant (A/B/C) + submit
- [ ] On vote: show confirmation toast ("Your vote recorded") but not others' votes
- [ ] After all votes: display results with selected Decision Maker highlighted
- [ ] Round 2 discussion can occur if voting doesn't complete round 1

## Implementation Notes
Chat messages are timestamped. Timer counts down from 60 seconds; auto-advance on expiry or manual "Ready" button. Voting is optional but recommended—results still displayed after timeout. Tie-break: randomly select winner from tied votes.
