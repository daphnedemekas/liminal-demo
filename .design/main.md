# Main

Ground-up rewrite: Liminal pivots from a learning/discovery platform to a project-based agent runner that shells out to Claude Code CLI. ~57k lines deleted, ~2k lines of new code.

## Review

**Verdict:** Needs work

### 1. `ChatPanel` tool_use event reads wrong field

`ChatPanel.tsx:45` reads `lastEvent.content.tool` but the executor emits `{"tools": [...]}`. The field should be `lastEvent.content.tools[0].tool`. Tool use messages will always show "Using tool: undefined".

### 2. Duplicate assistant messages on run completion

`ChatPanel.tsx` appends the result text on both the `result` event (line 55) and the `status: done` event (line 63). The run manager emits both, so the final answer appears twice. Pick one path.

### 3. `event_store.get_events()` detached session risk

When called without a `db` argument, `event_store.py:41-45` creates a local session, queries, closes the session, then returns ORM objects. Lazy attribute access on the returned `RunEvent` list will raise `DetachedInstanceError`. Currently safe because the only caller passes `db=`, but the standalone path is a latent bug.

### 4. No user ownership checks on endpoints

All project/run endpoints accept `user_id` from the client with no verification. Any caller can access any user's data by supplying a different ID. Auth endpoint auto-creates accounts for any name. Acceptable for local-only demo; needs addressing before any shared deployment.

## Design notes

- Complete product pivot. Old learning platform (discovery chat, teaching, trajectory, prompts, flows, scheduler) fully removed. New system: project management UI that runs Claude Code CLI as a subprocess.
- Architecture: FastAPI + SQLAlchemy ORM + SQLite backend. React + WebSocket frontend. Runs spawn `claude -p "instruction" --output-format stream-json` and stream events to the browser.
- Data model: UserProfile -> Projects -> AgentRuns -> RunEvents/Artifacts. Runs track cost, tokens, status lifecycle (planning -> working -> done/failed).
- `ClaudeCodeExecutor` is the core abstraction -- async wrapper around Claude Code CLI that parses stream-json into typed events.
- Database uses a single global engine via `get_engine()` singleton. Session factory shared across all modules.
- Frontend URLs support `VITE_API_URL` / `VITE_WS_URL` env vars with localhost fallbacks for local dev.
