# Testing Guide for Max Planck Project

## Manual Verification Checklist

### Flow 1: Creating and Joining a Session

1. Start containers:
   ```bash
   docker compose up --build -d
   ```

2. Open browser to http://localhost:3000/waiting

3. Generate new room code or enter custom one (e.g., `#room456`)

4. Verify lobby shows:
   - Current participants list
   - Time remaining countdown

### Flow 2: Discussion Round

1. Click on the session link in URL to enter experiment room

2. Type a message and press "Send Message"

3. Verify message appears for all connected clients in real-time (WebSocket)

4. Check WebSocket connection indicator in browser console (F12 → Console)

### Flow 3: Voting

1. After discussion period, system should transition to voting

2. Select a participant to vote for

3. Verify intermediate feedback shown ("Your vote recorded") without revealing others' votes

4. Results page should display after round completion

### Flow 4: Session Expiration

1. Start session with default timeout (~15 min inactivity)

2. Close browser tab, wait for timeout

3. Return and verify session status updated appropriately

## Playwright E2E Tests

Run with `npm test` or via MCP tooling when integrated.

### Test Cases

- [ ] Waiting room fills up from empty to 3 participants
- [ ] Discussion rounds progress (chat messages appear in real-time)
- [ ] Voting works and results display correctly after each round
- [ ] Session timeout expiration behavior triggers cleanup

## Skipped Test Scenarios

- **Network failure**: Requires mocking network stack; manual test with offline browser sufficient
- **Tie-breaking logic**: Edge case for equal votes (arbitrary winner selected per spec)
- **Rich markdown rendering**: Out of scope; plain text only

## Mock vs Real LLM Testing

### With Mock (Deterministic)

```bash
MOCK_LLM=true docker compose up --build -d
```

Useful for reproducible testing; same inputs yield same outputs.

### With Real API Calls

```bash
MOCK_LLM=false docker compose up --build -d
```

Requires valid LLM API credentials in environment variables.

## CI Script Location

`docker/test-ci.sh` handles basic container lifecycle and health checks.

Extend with Playwright integration when needed.
