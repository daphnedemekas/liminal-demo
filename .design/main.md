# Main

Ground-up rewrite: Liminal pivots from a learning/discovery platform to a project-based agent runner that shells out to Claude Code CLI. ~57k lines deleted, ~2k lines of new code.

## Review

**Verdict:** Ready to land

### Fixed

1. **ChatPanel tool_use field** — Fixed `ChatPanel.tsx` to read `content.tools[0].tool` instead of `content.tool`, matching the executor's output shape.
2. **Duplicate assistant messages** — Removed the redundant message append from the `status: done` handler; the `result` event path is the single source of the final answer.
3. **event_store detached session** — Added `session.expunge_all()` before closing the local session in `get_events()` so returned ORM objects remain usable.

### Known (not blocking)

4. **No user ownership checks on endpoints** — All project/run endpoints accept `user_id` from the client with no verification. Acceptable for local-only demo; needs addressing before any shared deployment.

## Design notes

- Complete product pivot. Old learning platform (discovery chat, teaching, trajectory, prompts, flows, scheduler) fully removed. New system: project management UI that runs Claude Code CLI as a subprocess.
- Architecture: FastAPI + SQLAlchemy ORM + SQLite backend. React + WebSocket frontend. Runs spawn `claude -p "instruction" --output-format stream-json` and stream events to the browser.
- Data model: UserProfile -> Projects -> AgentRuns -> RunEvents/Artifacts. Runs track cost, tokens, status lifecycle (planning -> working -> done/failed).
- `ClaudeCodeExecutor` is the core abstraction -- async wrapper around Claude Code CLI that parses stream-json into typed events.
- Database uses a single global engine via `get_engine()` singleton. Session factory shared across all modules.
- Frontend URLs support `VITE_API_URL` / `VITE_WS_URL` env vars with localhost fallbacks for local dev.
