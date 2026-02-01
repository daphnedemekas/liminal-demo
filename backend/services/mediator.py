"""Structured mediator: extract signals → rank action → generate response.

Three-step pipeline per turn:
1. EXTRACT — focused LLM call pulls structured signals from conversation
2. RANK — rule-based logic decides: ask_question | propose_plan | escalate
3. GENERATE — focused LLM call produces response for the chosen action
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import ChatMessage, Project, AgentRun, UserProfile
from backend.services.llm import chat, chat_json, parse_json
from backend.services.prompt_builder import build_system_prompt, build_synthesis_prompt

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────

SIGNAL_EXTRACTION_PROMPT = """\
You are analyzing a project conversation. Extract structured signals from the latest exchange.

Conversation:
{conversation}

Latest user message: {latest_message}

Existing signals: {existing_signals}

Extract and return a JSON object with these fields (merge with existing — keep what's there, add new):
- "intent": string — what the user is trying to accomplish (update if clearer now)
- "constraints": list of strings — budget, timeline, preferences, requirements mentioned
- "decisions_made": list of strings — things the user has confirmed or chosen
- "open_questions": list of strings — things still unclear that MUST be answered before work can begin
- "needs": list of strings — specific things they need help with
- "goals": list of strings — what they're trying to achieve

IMPORTANT rules for open_questions:
- REMOVE any question from open_questions that the user has now answered (even partially)
- Only include questions that are truly BLOCKING — things you absolutely cannot proceed without
- Do NOT invent nice-to-have questions. If you have enough to start working, open_questions should be EMPTY.
- When the user selects a specific option or gives a clear direction, that resolves the question — remove it.

Return ONLY the JSON object."""

ASK_QUESTION_PROMPT = """\
You are a conversational planning partner. Based on what you know, ask 1-2 focused follow-up questions.

{base_prompt}

## What we know so far
{signals}

## Open questions to resolve
{open_questions}

## Conversation so far
{conversation}

Ask 1-2 specific, focused questions to resolve the most important open questions.
Do NOT present generic menu options. Ask real questions about THEIR situation.

IMPORTANT: When you present distinct options or choices for the user to pick from, you MUST
include them as actions so they render as clickable buttons. Each action needs:
- "label": short button text (e.g. "Start with research")
- "description": one-line explanation
- "action_text": what gets sent as the user's reply if they click it

If your question is open-ended with no distinct choices, use an empty actions array.

Respond with JSON:
{{"message": "your question(s)", "actions": [{{"label": "Option label", "description": "What this means", "action_text": "The reply text"}}], "escalate": false, "task_description": ""}}

Return ONLY the JSON object."""

PROPOSE_PLAN_PROMPT = """\
You are a conversational planning partner. Based on what you've learned, propose a concrete plan.

{base_prompt}

## What we know
{signals}

## Conversation so far
{conversation}

Propose a concrete, numbered action plan based on everything you've learned.
Be specific — reference actual details from the conversation.
End with action buttons so the user can approve or adjust.

Respond with JSON:
{{"message": "your plan proposal", "actions": [{{"label": "Looks good, let's go", "description": "Approve this plan and start working", "action_text": "Looks good, let's go"}}, {{"label": "I want to adjust something", "description": "Modify the plan before starting", "action_text": "I want to adjust something"}}], "escalate": false, "task_description": ""}}

Return ONLY the JSON object."""

ESCALATE_PROMPT = """\
You are handing off to an execution agent. Write a detailed task description.

{base_prompt}

## What we know
{signals}

## Conversation so far
{conversation}

Write a brief confirmation message and a detailed task_description that contains
everything the agent needs to do the work without talking to the user again.
Include: goal, constraints, decisions made, specific requirements.

Respond with JSON:
{{"message": "your brief confirmation", "actions": [], "escalate": true, "task_description": "detailed task description here"}}

Return ONLY the JSON object."""

GREETING_PROMPT = """\
You are Liminal, a personal AI assistant.

{base_prompt}

{run_context}

The user just opened the project "{project_name}". {greeting_instruction}

Respond with JSON:
{{"message": "your greeting", "actions": [], "escalate": false, "task_description": ""}}

Return ONLY the JSON object."""

APPROVAL_PHRASES = [
    "looks good", "let's go", "go ahead", "do it", "approve", "approved",
    "sounds good", "perfect", "yes", "yep", "yeah", "ship it", "lgtm",
    "go for it", "start working", "let's do it", "proceed",
]


# ── Main entry point ─────────────────────────────────────────────────

def mediate(project_id: int, user_message: Optional[str], db: Session) -> dict:
    """Process a user message through the structured mediation pipeline.

    Returns dict with keys: message, actions, escalate, task_description
    """
    project, user, recent, recent_runs = _load_context(project_id, db)
    messages = [{"role": m.role, "content": m.content} for m in recent]
    base_prompt = build_system_prompt(user, project)

    # Greeting case — no user message, but only if no assistant message exists yet
    if not user_message:
        if any(m["role"] == "assistant" for m in messages):
            # Already greeted — return the last assistant message
            last = next(m for m in reversed(messages) if m["role"] == "assistant")
            return {"message": last["content"], "actions": [], "escalate": False, "task_description": ""}
        return _handle_greeting(project, user, messages, recent_runs, base_prompt, db)

    # Save user message
    db.add(ChatMessage(project_id=project_id, role="user", content=user_message))
    db.flush()
    messages.append({"role": "user", "content": user_message})

    # Count user turns in this conversation
    turn_count = sum(1 for m in messages if m["role"] == "user")

    existing_signals = project.conversation_signals or {}

    # Fast path: skip extraction for clear approval messages
    if _user_approved(user_message) and (existing_signals.get("decisions_made") or not existing_signals.get("open_questions")):
        merged = existing_signals
        action = "escalate"
    else:
        # Step 1: Extract signals (uses fast mini model)
        try:
            new_signals = _extract_signals(messages, user_message, existing_signals)
            merged = _merge_signals(existing_signals, new_signals)
        except Exception as e:
            logger.warning(f"Signal extraction failed: {e}")
            merged = existing_signals

        # Persist signals on project
        project.conversation_signals = dict(merged)
        db.flush()

        # Feed signals back to user profile
        _update_user_signals(user, merged, db)

        # Step 2: Rank — decide what action to take
        action = _rank(merged, turn_count, user_message)

    # Step 3: Generate response for the chosen action
    try:
        result = _generate(action, merged, messages, base_prompt)
    except Exception as e:
        logger.warning(f"Generation failed: {e}")
        result = {
            "message": "Let me work on that.",
            "actions": [],
            "escalate": True,
            "task_description": user_message or f"Get started on {project.name}",
        }

    # Normalize
    result.setdefault("message", "")
    result.setdefault("actions", [])
    result.setdefault("escalate", False)
    result.setdefault("task_description", "")

    # Save assistant message
    db.add(ChatMessage(
        project_id=project_id,
        role="assistant",
        content=result["message"],
        actions=result["actions"],
    ))
    db.commit()

    return result


# ── Internal helpers ─────────────────────────────────────────────────

def _load_context(project_id: int, db: Session):
    """Load project, user, recent messages, and recent runs."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    user = db.query(UserProfile).filter_by(id=project.user_id).first()
    if not user:
        raise ValueError(f"User not found for project {project_id}")

    recent = (
        db.query(ChatMessage)
        .filter_by(project_id=project_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    recent.reverse()

    recent_runs = (
        db.query(AgentRun)
        .filter_by(project_id=project_id)
        .order_by(AgentRun.created_at.desc())
        .limit(3)
        .all()
    )

    return project, user, recent, recent_runs


def _extract_signals(messages: list[dict], latest_message: str, existing_signals: dict) -> dict:
    """LLM call #1: extract structured signals from the conversation.

    Uses mini model for speed — this is structured extraction, not creative generation.
    """
    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:])
    prompt = SIGNAL_EXTRACTION_PROMPT.format(
        conversation=conversation,
        latest_message=latest_message,
        existing_signals=json.dumps(existing_signals),
    )
    return chat_json(prompt)


def _merge_signals(existing: dict, new: dict) -> dict:
    """Merge new signals into existing, deduplicating list fields."""
    merged = {**existing}
    for key, value in new.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            # Append and deduplicate
            seen = set()
            deduped = []
            for item in merged[key] + value:
                item_key = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
                if item_key not in seen:
                    seen.add(item_key)
                    deduped.append(item)
            merged[key] = deduped
        else:
            merged[key] = value
    return merged


def _rank(signals: dict, turn_count: int, latest_message: str) -> str:
    """Rule-based decision: ask_question, propose_plan, or escalate."""
    open_questions = signals.get("open_questions", [])
    decisions_made = signals.get("decisions_made", [])

    # Check for explicit approval
    if _user_approved(latest_message):
        if decisions_made or not open_questions:
            return "escalate"

    # Always ask at least one follow-up on the first user message
    if turn_count <= 1:
        return "ask_question"

    # If intent is clear and no open questions, propose a plan
    if signals.get("intent") and not open_questions:
        return "propose_plan"

    # If we have decisions and intent, propose even with some open questions
    if signals.get("intent") and decisions_made and turn_count >= 3:
        return "propose_plan"

    # If questions remain and we haven't looped too long, keep asking
    if open_questions and turn_count < 4:
        return "ask_question"

    # After 4+ turns, propose a plan anyway
    if turn_count >= 4:
        return "propose_plan"

    # Default: keep asking
    return "ask_question"


def _user_approved(text: str) -> bool:
    """Check if the user's message indicates plan approval."""
    lower = text.lower().strip()
    return any(phrase in lower for phrase in APPROVAL_PHRASES)


def _generate(action: str, signals: dict, messages: list[dict], base_prompt: str) -> dict:
    """LLM call #2: generate a response for the chosen action."""
    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:])
    signals_str = json.dumps(signals, indent=2)
    open_questions = "\n".join(f"- {q}" for q in signals.get("open_questions", [])) or "None identified"

    if action == "ask_question":
        prompt = ASK_QUESTION_PROMPT.format(
            base_prompt=base_prompt,
            signals=signals_str,
            open_questions=open_questions,
            conversation=conversation,
        )
    elif action == "propose_plan":
        prompt = PROPOSE_PLAN_PROMPT.format(
            base_prompt=base_prompt,
            signals=signals_str,
            conversation=conversation,
        )
    elif action == "escalate":
        prompt = ESCALATE_PROMPT.format(
            base_prompt=base_prompt,
            signals=signals_str,
            conversation=conversation,
        )
    else:
        raise ValueError(f"Unknown action: {action}")

    raw = chat(prompt)
    return parse_json(raw)


def _handle_greeting(project, user, messages, recent_runs, base_prompt, db) -> dict:
    """Handle the greeting case when user opens a project with no message."""
    run_context = ""
    if recent_runs:
        run_context = "## Recent work in this project"
        for run in recent_runs:
            goal_snippet = (run.goal or "")[:200]
            result_snippet = (run.result_summary or "")[:300]
            run_context += f"\n- Goal: {goal_snippet}"
            if result_snippet:
                run_context += f"\n  Result: {result_snippet}"
        greeting_instruction = "Welcome them back briefly, remind them where things stand, and ask what they'd like to focus on next."
    else:
        greeting_instruction = "Greet them briefly and ask a specific question to understand what they're trying to accomplish. Don't present generic options — start a real conversation."

    prompt = GREETING_PROMPT.format(
        base_prompt=base_prompt,
        run_context=run_context,
        project_name=project.name,
        greeting_instruction=greeting_instruction,
    )

    try:
        raw = chat(prompt)
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Greeting LLM call failed: {e}")
        result = {
            "message": f"Hey! What are you looking to do with {project.name}?",
            "actions": [],
            "escalate": False,
            "task_description": "",
        }

    result.setdefault("message", "")
    result.setdefault("actions", [])
    result.setdefault("escalate", False)
    result.setdefault("task_description", "")

    db.add(ChatMessage(
        project_id=project.id,
        role="assistant",
        content=result["message"],
        actions=result["actions"],
    ))
    db.commit()

    return result


def synthesize_result(run: AgentRun, project: Project, user: UserProfile, db: Session) -> dict:
    """Synthesize raw agent output into a personalized summary with artifacts.

    Returns dict with keys: summary, artifacts, suggested_next_steps, actions
    """
    # Load recent chat messages for context
    recent = (
        db.query(ChatMessage)
        .filter_by(project_id=project.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    recent.reverse()
    conversation = [{"role": m.role, "content": m.content} for m in recent]

    prompt = build_synthesis_prompt(
        user=user,
        project=project,
        goal=run.goal,
        raw_result=run.result_summary or "",
        conversation=conversation,
        explanation_pref=user.explanation_preference,
    )

    try:
        raw = chat(prompt)
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Synthesis LLM call failed: {e}")
        result = {
            "summary": run.result_summary or "The task completed.",
            "artifacts": [],
            "suggested_next_steps": [],
            "actions": [],
        }

    result.setdefault("summary", "")
    result.setdefault("artifacts", [])
    result.setdefault("suggested_next_steps", [])
    result.setdefault("actions", [])

    # Persist artifacts (upsert: update existing artifact if same project + type + title)
    from backend.database import Artifact
    for art in result["artifacts"]:
        a_type = art.get("type", "report")
        a_title = art.get("title", "Untitled")
        existing = db.query(Artifact).filter(
            Artifact.project_id == project.id,
            Artifact.artifact_type == a_type,
            Artifact.title == a_title,
        ).first()
        if existing:
            existing.content = art.get("content", "")
            existing.sources = [{"url": s} for s in art.get("sources", []) if isinstance(s, str)]
            existing.run_id = run.run_id
        else:
            db.add(Artifact(
                run_id=run.run_id,
                project_id=project.id,
                artifact_type=a_type,
                title=a_title,
                content=art.get("content", ""),
                sources=[{"url": s} for s in art.get("sources", []) if isinstance(s, str)],
            ))

    # Save synthesis summary as assistant message
    db.add(ChatMessage(
        project_id=project.id,
        role="assistant",
        content=result["summary"],
        actions=result.get("actions", []),
        run_id=run.run_id,
    ))
    db.commit()

    return result


def _update_user_signals(user, new_signals: dict, db: Session):
    """Feed conversation signals back into user.onboarding_info."""
    try:
        existing = json.loads(user.onboarding_info) if user.onboarding_info else {}
    except (json.JSONDecodeError, TypeError):
        existing = {}

    updated = False
    for key in ("needs", "goals", "constraints"):
        new_values = new_signals.get(key, [])
        if not new_values or not isinstance(new_values, list):
            continue
        old_values = existing.get(key, [])
        if not isinstance(old_values, list):
            old_values = []
        merged = list(dict.fromkeys(old_values + new_values))  # dedupe preserving order
        if merged != old_values:
            existing[key] = merged
            updated = True

    if updated:
        user.onboarding_info = json.dumps(existing)
        db.flush()
