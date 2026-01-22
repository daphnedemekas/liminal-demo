# Refactor

Prompt system refactor introducing structured prompt assembly, token management, and concurrency scheduling.

## Review

**Verdict:** Needs work

### Issues

1. **Prompt template placeholders still present but never filled.** The prompts now reference `<lf:schema>`, `<lf:conversation>`, and `<lf:goal_context>` tags (e.g., `generate_controller.txt:4` says "See <lf:schema> for the full schema state"), but `assemble_prompt()` never replaces these placeholders. The `format_prompt()` function generates actual `<lf:schema>` XML blocks, so the LLM sees both the instruction to "See <lf:schema>" and the actual content—redundant and potentially confusing. Either remove the placeholder text from prompts or keep the original `{schema}` format variables.

2. **Scheduler acquire/release mismatch.** In `goal_discovery_ranker.py:403-459` and `teaching_candidate_ranker.py:438-500`, the code acquires scheduler slots but wraps releases in `if acquired_branch:` guards. However, `acquired_branch` is always set because `acquire()` was called before the `if`. The variable name suggests a boolean check for "was this acquired," but the code path ensures it's always true after `scheduler.acquire()` returns. This isn't a bug but is misleading—consider renaming or removing the guard since `scheduler.release()` uses `discard()` and is safe to call redundantly.

3. **`communication_style` defensive code duplicated three times.** The same 15-line block ensuring `communication_style` has all required fields appears in:
   - `goal_discovery_ranker.py:484-500`
   - `teaching_candidate_ranker.py:514-530`
   - `orchestrator.py:93-104` and `orchestrator.py:643-651`

   Extract to a helper function like `ensure_communication_style_defaults(profile_dict)`.

4. **Teaching candidate unlock logic nested 6 levels deep.** `backend/main.py:1093-1148` has a 55-line try block with 6 levels of nesting to mark teaching candidates complete. This is hard to follow. Consider extracting to a helper function or using early returns.

5. **tiktoken added to requirements but optional.** `requirements.txt` adds `tiktoken>=0.5.0` but `src/prompt/tokens.py` falls back to character estimation if tiktoken import fails. Either make tiktoken required (remove fallback) or mark it optional in requirements with a comment.

6. **`_format_conversation` now just delegates.** `ranker_base.py:887-891` wraps `gather_conversation()` but the caller could call `gather_conversation()` directly. The method adds no value and obscures that the real implementation lives elsewhere.

### Missing

- No integration test verifying the full prompt assembly pipeline with real prompts (unit tests mock components).
- No test for `assemble_prompt()` function in `src/prompt/assembly.py`.

## Design notes

### Prompt system architecture

The new system separates concerns:

- `gather.py`: Collects data into structured `PromptComponents`
- `formatter.py`: Serializes components to XML-tagged text
- `trim.py`: Token-aware truncation with priority-based dropping
- `assembly.py`: Orchestrates the pipeline

Priorities for trimming (lowest dropped first):
1. `docs` - project documentation
2. `conversation` - older messages trimmed first
3. `user_background` - user context
4. `goal_context` - goal-specific data
5. `schema` - current state
6. `step` - never dropped
7. `system_instructions` - never dropped

### Scheduler design

Global singleton scheduler coordinates parallel LLM calls across agents. Default limits: 3 concurrent, 15 global. Used during parallel Phase 1 calls (branch + profile + themes). Acquire/release pattern with thread-safe locking.

### Flow system

Pydantic models for DAG-based multi-step execution:
- `Flow`: Step list wrapper
- `FlowStep`: Single step with optional fork/choose/join
- `FlowDef`: Named flow with steps

Supports sequential, fork-join, and prompt-driven choice patterns. Not yet integrated with main application—appears to be scaffolding for future pipeline execution.
