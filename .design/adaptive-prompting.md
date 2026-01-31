# Adaptive Prompting

## What to build

Wire user model data into every agent execution so the AI is personalized, proactive, and adapts its ask-vs-do ratio per user and project. Make opening a project feel like returning to an assistant who's been working for you.

## Current state (problems)

1. **User model collected but never used.** Onboarding gathers needs, pain_points, goals, domain_knowledge, involvement preference, explanation preference. The system prompt sent to Claude Code is hardcoded and ignores all of it.
2. **No conversation continuity.** Each run is a blank slate. Previous run results aren't passed as context, so the AI can't reference what it already did.
3. **No proactive behavior.** When you open a project, you see an empty chat waiting for input. The AI never initiates — no "here's what I found since last time," no "I noticed X, want me to look into it?"
4. **No ask-vs-do calibration.** A hands-off user and an involved user get identical treatment. No adaptation over time.
5. **UserModelService exists but is never called.** Dead code.

## Architecture

Two changes, both backend. Frontend gets minor tweaks.

### 1. Prompt assembly layer (new: `prompt_builder.py`)

Sits between `run_manager` and `claude_code_executor`. Builds a personalized system prompt + enriched instruction from user model + project history.

```python
# backend/services/prompt_builder.py

def build_system_prompt(user: UserProfile, project: Project) -> str:
    """Assemble a personalized system prompt from user model data."""
    ...

def build_instruction(
    user: UserProfile,
    project: Project,
    raw_goal: str,
    recent_runs: list[AgentRun],
) -> str:
    """Enrich the user's raw message with project context and history."""
    ...
```

**System prompt structure:**

```
You are Liminal, a personal AI assistant for {user.name}.
{base capabilities — web search, files, code execution, etc.}

## About this person
{user.model_summary}
Domains: {user.known_domains}  # e.g. {"cooking": "expert", "finance": "novice"}

## How they like to work
Involvement: {involvement_level}  # from project or user default
- hands_off: Do the work, present results. Only ask if you'd be blocked without an answer.
- check_ins: Do the work, but pause at key decision points to confirm direction.
- involved: Think out loud. Present options before acting. Explain your reasoning.

Output style: {explanation_preference}
- just_results: Deliverables only. No process narration.
- brief_summary: Short explanation of what you did and why, then results.
- show_your_work: Full reasoning, sources, alternatives considered.

## This project
Name: {project.name}
Description: {project.description}

{if recent_runs:}
## What's happened so far
{for run in recent_runs[-3:]:}
- Goal: {run.goal[:200]}
  Result: {run.result_summary[:300]}
{end}

Build on previous work. Don't repeat research already done.
{end}
```

**Instruction enrichment** — for auto-start / proactive kicks:

```python
def build_proactive_instruction(user: UserProfile, project: Project, recent_runs: list[AgentRun]) -> str:
    """Generate instruction for when the AI initiates (project open, return visit)."""
    if not recent_runs:
        # First visit — research and orient
        return (
            f'You are starting work on "{project.name}". '
            f'Context: {project.description} '
            f'Do initial research, then present a clear summary of what you found '
            f'and 2-3 concrete next steps the user can pick from.'
        )
    else:
        # Returning — summarize progress and suggest next actions
        last = recent_runs[-1]
        return (
            f'The user is returning to "{project.name}". '
            f'Last time, the goal was: {last.goal[:200]} '
            f'Result: {last.result_summary[:500]} '
            f'Briefly welcome them back, summarize where things stand, '
            f'and suggest 2-3 things you could do next. Be concise.'
        )
```

### 2. Wire into run creation (`runs.py` + `run_manager.py`)

The `create_run` endpoint already has access to project and user. Load user profile + recent runs, call prompt_builder, pass enriched instruction + personalized system prompt to executor.

```python
# In runs.py create_run():
user = db.query(UserProfile).filter_by(id=project.user_id).first()
recent_runs = db.query(AgentRun).filter_by(project_id=req.project_id).order_by(AgentRun.created_at.desc()).limit(3).all()

system_prompt = build_system_prompt(user, project)
instruction = build_instruction(user, project, req.goal, recent_runs)

run = AgentRun(project_id=req.project_id, user_id=project.user_id, goal=req.goal)
# Store the enriched versions for the executor
```

```python
# In ClaudeCodeExecutor.execute(): accept system_prompt as parameter instead of using hardcoded
async def execute(self, instruction: str, system_prompt: str = None, ...):
    cmd = [
        "claude", "-p", instruction,
        "--output-format", "stream-json",
        "--verbose",
        "--system-prompt", system_prompt or self.SYSTEM_PROMPT,
    ]
```

### 3. Activate UserModelService (existing code, just wire it)

Call `user_model_service.update_model(user_id)` at the end of each completed run in `run_manager._execute_run()`. It already exists — just add the call after `run.status = "done"`.

This keeps the model_summary, known_domains, and suggested preferences fresh as the user interacts.

### 4. Proactive project greeting (frontend)

When ChatPanel mounts for any project (not just suggested ones), fetch a greeting from a new lightweight endpoint:

```python
# New endpoint: GET /api/projects/{id}/greeting
@router.get("/{project_id}/greeting")
async def project_greeting(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(id=project_id).first()
    user = db.query(UserProfile).filter_by(id=project.user_id).first()
    recent_runs = db.query(AgentRun).filter_by(project_id=project_id).order_by(AgentRun.created_at.desc()).limit(3).all()

    instruction = build_proactive_instruction(user, project, recent_runs)
    system_prompt = build_system_prompt(user, project)

    # Use executor with max_turns=1 for a fast, single-turn greeting
    run = AgentRun(project_id=project_id, user_id=project.user_id, goal=instruction)
    # ... execute and return the greeting text
```

Frontend change in `ChatPanel.tsx`:
- On mount, call `/api/projects/{id}/greeting`
- Display greeting as first assistant message
- Replace the static "What would you like help with?" empty state
- Keep it fast: `max_turns=1` so it's a single LLM response, no tool use

### 5. Speed: `--max-turns` for greetings

Greetings use `max_turns=1` to avoid tool calls. Just a fast text response using the context already in the prompt. Regular runs remain unbounded.

## Data structures

No new tables. Changes to existing:

```python
# AgentRun — add field to store the enriched instruction (for debugging/replay)
class AgentRun(Base):
    # existing fields...
    enriched_instruction = Column(Text, nullable=True)  # what was actually sent to CLI
    system_prompt_hash = Column(String, nullable=True)   # for debugging prompt changes
```

```python
# ClaudeCodeExecutor.execute() signature change:
async def execute(
    self,
    instruction: str,
    system_prompt: str | None = None,  # NEW — overrides default
    working_dir: str = ".",
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
) -> AsyncIterator[ExecutorEvent]:
```

## Key functions

```python
# prompt_builder.py
def build_system_prompt(user: UserProfile, project: Project) -> str:
    """Personalized system prompt from user model + project context."""

def build_instruction(user: UserProfile, project: Project, raw_goal: str, recent_runs: list[AgentRun]) -> str:
    """Enrich raw user message with conversation history and project state."""

def build_proactive_instruction(user: UserProfile, project: Project, recent_runs: list[AgentRun]) -> str:
    """Generate AI-initiated message for project open / return visits."""
```

```python
# runs.py — modified
async def create_run(req: RunCreate, db):
    """Now loads user profile + recent runs, builds personalized prompt."""

# projects.py — new endpoint
async def project_greeting(project_id: int, db):
    """Fast single-turn greeting when user opens a project."""
```

## Constraints

- **System prompt must stay under ~2000 tokens.** Claude Code has its own system prompt overhead. Keep user context tight — summaries, not raw data. If model_summary + known_domains + recent run summaries exceed this, truncate recent runs first.
- **Greeting must feel instant.** Use `max_turns=1`, no tools. If Claude Code CLI cold-start is too slow, consider using the `llm.py` chat function for greetings instead (direct API call, ~1s vs CLI startup overhead).
- **Don't break the existing onboarding flow.** Prompt builder gracefully handles empty/null user model fields — falls back to the current generic prompt.
- **involvement_level cascades:** project-level overrides user-level default. If project.involvement_level is null, use user.default_involvement.

## Files to change

| File | Change |
|------|--------|
| `backend/services/prompt_builder.py` | **NEW** — prompt assembly |
| `backend/services/claude_code_executor.py` | Accept `system_prompt` param |
| `backend/services/run_manager.py` | Pass enriched prompt to executor; call user_model_service after runs |
| `backend/routers/runs.py` | Load user + history, call prompt_builder |
| `backend/routers/projects.py` | New `/greeting` endpoint |
| `frontend/src/components/ChatPanel.tsx` | Fetch greeting on mount; remove static empty state |

## Done when

1. Open a project with prior runs → AI greets with summary of last session + suggestions
2. Open a new suggested project → AI does research and presents options (already works, but now personalized)
3. `hands_off` user gets results with minimal questions; `involved` user gets options presented before action
4. After 5+ runs, `user.model_summary` and `known_domains` are populated and reflected in prompts
5. Greeting loads in <3 seconds

```bash
# Verify prompt personalization is working:
# 1. Create a user, complete onboarding
# 2. Open a project, send a message
# 3. Check the AgentRun.enriched_instruction field — should contain user context
# 4. Close and reopen the project — should see a proactive greeting referencing prior work
```
