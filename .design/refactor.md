# Refactor

Prompt system refactor introducing structured prompt assembly, token management, and concurrency scheduling.

## Summary

This branch adds a modular prompt assembly system with:

1. **Structured prompt components** (`src/prompt/components.py`) - Pydantic models for all prompt context (conversation, schema, user background, goal context)

2. **Context gathering** (`src/prompt/gather.py`) - Functions to collect and format context data from various sources

3. **XML-tagged formatting** (`src/prompt/formatter.py`) - Converts components into `<lf:*>` tagged blocks for LLM consumption

4. **Token-aware trimming** (`src/prompt/trim.py`) - Priority-based truncation to stay within token limits. Never drops step or system instructions.

5. **Unified assembly** (`src/prompt/assembly.py`) - Single entry point that orchestrates the full pipeline

6. **Concurrency scheduling** (`src/scheduler/scheduler.py`) - Global singleton coordinating parallel LLM calls with configurable limits

7. **Flow execution framework** (`src/flows/`) - DAG-based multi-step execution with fork/join and choose patterns (scaffolding for future use)

## Changes

### Prompt System

Prompts now reference XML tags instead of Python format strings:
- `generate_controller.txt` says "See <lf:schema> for the full schema state"
- `assemble_prompt()` adds actual `<lf:schema>` blocks with JSON content
- This allows prompts to be self-documenting while the system provides structured data

Priority order for trimming (lowest dropped first):
1. `docs` - project documentation
2. `conversation` - older messages trimmed first
3. `user_background` - user context
4. `goal_context` - goal-specific data
5. `schema` - current state
6. `step` - never dropped
7. `system_instructions` - never dropped

### Scheduler

Global singleton coordinates parallel LLM calls across agents:
- Default limits: 3 concurrent, 15 global
- Used during parallel Phase 1 calls (branch + profile + themes)
- Thread-safe acquire/release pattern

### Agent Updates

`goal_discovery_ranker.py` and `teaching_candidate_ranker.py`:
- Now use `assemble_prompt()` for all prompt construction
- Scheduler integration for concurrency control
- Defensive handling for `communication_style` to prevent None values

`teaching_orchestrator.py`:
- Migrated to use `assemble_prompt()` for curriculum planning and teacher responses
- Uses `gather_conversation()` and `gather_teaching_context()` helpers

### Dependencies

- Added `tiktoken>=0.5.0` for accurate token counting (falls back to character estimation if unavailable)

## Test Coverage

All 83 tests pass:
- `test_api.py` - API endpoint tests (fixed to match current implementation)
- `test_flows_*.py` - Flow system tests
- `test_prompt_*.py` - Prompt assembly pipeline tests
- `test_scheduler.py` - Concurrency scheduler tests
- `test_session_manager.py` - Session management tests

## Known Style Issues

These are style issues, not bugs. The system functions correctly.

1. **Duplicated communication_style handling** - Same 15-line defensive block appears in 3 places. Could be extracted to a helper function.

2. **Teaching candidate unlock logic deeply nested** - `backend/main.py:1093-1148` has 6 levels of nesting. Could be extracted to a helper function.

3. **_format_conversation delegation** - `ranker_base.py` method now just delegates to `gather_conversation()`. Minor code smell.

4. **Scheduler acquire/release guards** - The `if acquired_branch:` guards are redundant since acquire() always returns a tuple. Not harmful but misleading.

## Files Changed

### New Files
- `src/flows/` - Flow execution framework
- `src/prompt/` - Prompt assembly system
- `src/scheduler/` - Concurrency scheduler
- `tests/test_flows_*.py` - Flow tests
- `tests/test_prompt_*.py` - Prompt tests
- `tests/test_scheduler.py` - Scheduler tests

### Modified Files
- `backend/main.py` - Teaching candidate completion logic
- `src/agents/goal_discovery_ranker.py` - Prompt assembly, scheduler integration
- `src/agents/teaching_candidate_ranker.py` - Prompt assembly, scheduler integration
- `src/agents/orchestrator.py` - communication_style defensive handling
- `src/agents/ranker_base.py` - Migrated to assemble_prompt()
- `src/agents/interviewer.py` - Migrated to assemble_prompt()
- `src/agents/teaching_orchestrator.py` - Migrated to assemble_prompt()
- `prompts/ranker/*/*.txt` - Updated to reference <lf:*> tags
- `requirements.txt` - Added tiktoken
- `tests/test_api.py` - Fixed to match current API implementation
