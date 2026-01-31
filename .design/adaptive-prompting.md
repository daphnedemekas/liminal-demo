# Adaptive Prompting

Personalized system prompts, proactive greetings, auto-kickoff for suggested projects, and user model updates wired into the run lifecycle.

## Review

**Verdict:** Ready to ship

Implementation is clean and follows the design. Three minor issues noted below — none blocking.

1. **Greeting endpoint blocks on LLM call.** `project_greeting` is `async def` but calls `chat()` synchronously, tying up the event loop for the duration of the LLM call. For a local demo this is fine; for concurrent users, wrap in `asyncio.to_thread(chat, prompt)` or use an async LLM client.

2. **Greeting races with auto-kickoff on fresh suggested projects.** The greeting effect checks `project.suggested_by_system && project.run_count === 0` to skip, and the auto-kickoff effect checks the same condition to fire. Both depend on `hasAutoStarted` as a guard, so they won't collide in practice — but the logic is subtle. A single effect that decides "greeting vs kickoff" would be clearer.

3. **`run_manager` queries inside an already-open session.** `_execute_run` opens its own session via `get_session_factory()()` and queries `Project` + `UserProfile` + recent `AgentRun`s. This is consistent with how the rest of `run_manager` works (it owns its session), but worth noting that `create_run` in `runs.py` does *not* pass the personalized prompt — the enrichment happens entirely in `run_manager`. This is actually a good separation; just calling it out since the design doc suggested doing it in `runs.py`.

## Design notes

- `prompt_builder.py` is the new prompt assembly layer. Three public functions: `build_system_prompt`, `build_instruction`, `build_proactive_instruction`. Involvement level cascades project -> user default. All fields handled gracefully when null/empty.
- Greeting uses `llm.chat()` (direct API call) rather than Claude Code CLI, avoiding CLI cold-start latency. Matches the design constraint about speed.
- `UserModelService.update_model()` is called after each successful run in `run_manager._execute_run()`. Failures are caught and logged, not propagated.
- `ChatPanel` now receives the full `Project` object instead of `projectId`/`projectName`, which is cleaner for the greeting and auto-kickoff logic.
- Onboarding suggestion prompt improved to generate broader project areas instead of narrow tasks.
