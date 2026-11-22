# GLOSSARY.md - Domain Model Terms

| Term | Definition |
|------|------------|
| Session | An experiment instance identified by a random room code (e.g., `room456`). Contains participants, rounds, and votes. Status: `waiting` → `active` → `completed`. |
| Participant | An entity in a session, either human or AI agent. Identified by sequential ID ("Player A", "Player B") within its session. |
| Round | A discrete discussion period (~1 minute) with chat history and voting results. Auto-numbered per session. |
| Vote | A participant's selection of a target participant for Decision Maker role. Blind voting until results revealed. |
| Human | Real user connecting via web browser |
| AI | Synthetic participant powered by LLM following configured prompts |
| Room Code | URL-safe identifier for session (random or custom) |
| Waiting Room | Lobby where participants join and await other players filling slots |
