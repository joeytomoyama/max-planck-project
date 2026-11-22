# Testing

## Manual checklist

### Real LLM via a local Ollama

1. Install [Ollama](https://ollama.com) on the host and pull a model, e.g.
   `ollama pull qwen3.5:9b`. Check it answers:
   `curl http://localhost:11434/v1/models`.
2. In `config.yml` set `mock_mode: false` and `condition: 1_human_2_ai`. For a
   thinking model (qwen3 family) uncomment `reasoning_effort: none` under
   `llm_parameters:`.
3. Start with the LLM env vars (or put them in `.env`):
   ```
   LLM_BASE_URL=http://host.docker.internal:11434/v1 LLM_MODEL=qwen3.5:9b docker compose up --build
   ```
   PowerShell: `$env:LLM_BASE_URL="http://host.docker.internal:11434/v1"; $env:LLM_MODEL="qwen3.5:9b"; docker compose up --build`
4. Open `/waiting`, create a Session, open the share link in another tab.
   - [ ] Both AI Agents post an opening message in each Discussion Phase, in
         short casual English that fits the chat (not the mock lines from
         `backend/app/llm.py`).
   - [ ] Writing "are you a bot?" gets no admission of being an AI.
   - [ ] The app log shows `POST .../chat/completions "HTTP/1.1 200 OK"` and, at
         voting, no `votes at random` lines (the LLM's Vote was parsed).
   - [ ] The Session reaches the Result.
5. Failure path: stop Ollama (or set `LLM_BASE_URL` to a port nothing listens
   on) and run another Session.
   - [ ] AI Agents send nothing, the log shows `LLM call failed, message skipped`
         and `votes at random`, and the Session still reaches the Result.
6. Without `LLM_BASE_URL`/`LLM_MODEL` and with `mock_mode: false`:
   - [ ] the app refuses to start with a `CONFIG ERROR` naming the missing env vars.
7. Put `mock_mode: true` back.
