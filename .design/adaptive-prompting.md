# Adaptive Prompting

Personalized system prompts, proactive greetings, auto-kickoff for suggested projects, and user model updates wired into the run lifecycle.

## Status: Ready to land

## What shipped

- **`prompt_builder.py`** — prompt assembly layer with `build_system_prompt`, `build_instruction`, `build_proactive_instruction`, `build_synthesis_prompt`. Involvement level cascades project -> user default. All fields handled gracefully when null/empty.
- **`mediator.py`** — structured mediation pipeline (extract signals -> rank action -> generate response). Handles greetings, follow-up questions, plan proposals, and escalation to agent. Persists conversation signals on project and feeds them back to user profile.
- **`user_model_service.py`** — re-analyzes user interactions after each successful run to update model_summary, known_domains, and preferences.
- **Greeting endpoint** (`GET /api/projects/{id}/greeting`) — fast single-turn LLM greeting when user opens a project. Falls back to static text on failure.
- **Chat endpoint** (`POST /api/projects/{id}/chat`) — conversational mediation that can escalate to a full agent run.
- **`ChatPanel`** receives full `Project` object. Handles greeting loading, auto-kickoff for suggested projects, synthesis display with artifacts, and activity log.
- **`useRunStream`** extended to handle `synthesis` events from WebSocket.
- **Database** — added `enriched_instruction` and `system_prompt_hash` columns to `AgentRun`.
- **Onboarding** — suggestion prompt improved to generate broader project areas instead of narrow tasks.
- **Audio** — TTS endpoint, `useAudio` hook, mic/voice UI in ChatPanel. Speech recognition type declarations.

## Fixes applied during polish

1. **`mediator.py`** — removed hardcoded `model="gpt-5"` from `_generate()`, now uses default model via `chat()`.
2. **`speech.d.ts`** — expanded from stub `Window` interface to full ambient type declarations for `SpeechRecognition`, `SpeechRecognitionEvent`, `SpeechRecognitionResultList`, `SpeechRecognitionResult`, and `SpeechRecognitionAlternative`. Fixes three TypeScript compilation errors.
3. **`ChatPanel.tsx`** — fixed `ReactMarkdown` receiving `ArtifactContent` (which can be a structured object) instead of a string. Now coerces non-string content to JSON before rendering.

## Known limitations (not blocking)

1. **Greeting endpoint blocks on LLM call.** For concurrent users, should wrap in `asyncio.to_thread()` or use async LLM client.
2. **Greeting vs auto-kickoff logic is subtle.** Both use `hasAutoStarted` as guard but a single deciding effect would be clearer.
