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
from backend.services.llm import chat, chat_messages, parse_json, MODEL_MINI, MODEL_JSON
from backend.services.prompt_builder import build_system_prompt, build_synthesis_prompt
from backend.services.context_service import get_context_text
from backend.services.memory import extract_insights, retrieve_insights

from backend.prompts.mediator import (
    MEDIATOR_SIGNAL_EXTRACTION_PROMPT as SIGNAL_EXTRACTION_PROMPT,
    MEDIATOR_ASK_QUESTION_PROMPT as ASK_QUESTION_PROMPT,
    MEDIATOR_PROPOSE_PLAN_PROMPT as PROPOSE_PLAN_PROMPT,
    MEDIATOR_ESCALATE_PROMPT as ESCALATE_PROMPT,
    MEDIATOR_GREETING_PROMPT as GREETING_PROMPT,
    APPROVAL_PHRASES,
)

logger = logging.getLogger(__name__)


# ── Main entry point ─────────────────────────────────────────────────

def mediate(project_id: int, user_message: Optional[str], db: Session) -> dict:
    """Process a user message through the full mediation pipeline (extract + generate).

    Returns dict with keys: message, actions, escalate, task_description
    """
    extract_result = mediate_extract(project_id, user_message, db)

    # If extract returned an early result (greeting, cached), just return it
    if extract_result.get("_early_return"):
        result = extract_result
        result.pop("_early_return", None)
        return result

    return mediate_generate(extract_result, db)


def mediate_extract(project_id: int, user_message: Optional[str], db: Session) -> dict:
    """Extract phase: signals, action, context. Returns intermediate state for generate phase.

    Returns dict with _extract_state key containing: action, signals, messages, base_prompt, project_id, user_message
    Or returns a full result dict with _early_return=True for greeting/home cases.
    """
    # Home chat gets its own conversational flow — no plan/escalate pipeline
    project = db.query(Project).filter_by(id=project_id).first()
    if project and project.domain == "home":
        from backend.services.home import home_chat_extract
        return home_chat_extract(project_id, user_message, db)

    project, user, recent, recent_runs = _load_context(project_id, db)
    messages = [{"role": m.role, "content": m.content} for m in recent]
    base_prompt = build_system_prompt(user, project)

    # Inject user-uploaded context
    context_text = get_context_text(db, user.id, project_id=project_id)
    if context_text:
        base_prompt += f"\n\n{context_text}"

    # Inject memory insights
    memory = retrieve_insights(user.id, user_message or project.description, db)
    if memory:
        base_prompt += f"\n\n{memory}"

    # Greeting case — no user message, but only if no assistant message exists yet
    if not user_message:
        if any(m["role"] == "assistant" for m in messages):
            last = next(m for m in reversed(messages) if m["role"] == "assistant")
            return {"message": last["content"], "actions": [], "escalate": False, "task_description": "", "_early_return": True}
        result = _handle_greeting(project, messages, recent_runs, base_prompt, db)
        result["_early_return"] = True
        return result

    # Save user message
    db.add(ChatMessage(project_id=project_id, role="user", content=user_message))
    db.commit()
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

    # Note: research detection happens in generate phase (gpt-4o), not here
    return {
        "_extract_state": {
            "action": action,
            "signals": merged,
            "messages": messages,
            "base_prompt": base_prompt,
            "project_id": project_id,
            "user_id": user.id,
            "user_message": user_message,
            "project_name": project.name,
        },
    }


def mediate_generate(extract_result: dict, db: Session) -> dict:
    """Generate phase: produce response from extracted signals.

    Takes the output of mediate_extract (must have _extract_state key).
    Returns dict with keys: message, actions, escalate, task_description
    """
    state = extract_result["_extract_state"]

    # Home chat has its own generate path (no action/rank pipeline)
    if "action" not in state:
        from backend.services.home import home_chat_generate
        return home_chat_generate(extract_result, db)

    action = state["action"]
    signals = state["signals"]
    messages = state["messages"]
    base_prompt = state["base_prompt"]
    project_id = state["project_id"]
    user_id = state["user_id"]
    user_message = state["user_message"]
    project_name = state["project_name"]

    # Step 3: Generate response for the chosen action (retry once on failure)
    result = None
    for attempt in range(2):
        try:
            result = _generate(action, signals, messages, base_prompt)
            break
        except Exception as e:
            logger.warning(f"Generation attempt {attempt+1} failed: {e}")
    if result is None:
        result = {
            "message": "I'll start by researching what's out there — you'll see progress below as the agent works.",
            "actions": [],
            "escalate": True,
            "task_description": (
                user_message or
                f"Research the landscape for \"{project_name}\": existing tools, services, approaches, "
                f"pricing, and how well each fits the user's specific need. End with a clear recommendation: "
                f"either recommend the best existing tool and why, or explain the gap and offer to build custom. "
                f"Be opinionated. Do NOT build anything yet — just research and recommend."
            ),
        }

    # Normalize
    result.setdefault("message", "")
    result.setdefault("actions", [])
    result.setdefault("escalate", False)
    result.setdefault("task_description", "")
    result.setdefault("artifacts", [])
    # Keep research field — router will check it if extract phase missed it

    # Persist any artifacts the LLM created (e.g. rich content analysis)
    _persist_chat_artifacts(result.get("artifacts", []), project_id, db)

    # Save assistant message
    db.add(ChatMessage(
        project_id=project_id,
        role="assistant",
        content=result["message"],
        actions=result["actions"],
    ))
    db.commit()

    # Extract insights from this exchange
    if user_message:
        extract_insights(user_id, user_message, result["message"], "project", str(project_id), db)

    return result


# ── Internal helpers ─────────────────────────────────────────────────

def _persist_chat_artifacts(artifacts: list, project_id: int, db: Session):
    """Persist artifacts created by the LLM during chat (e.g. rich content analysis)."""
    if not artifacts:
        return
    from backend.database import Artifact
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        a_type = art.get("type", "report")
        a_title = art.get("title", "Analysis")
        a_content = art.get("content", "")
        # Upsert: update existing artifact with same project + type + title
        existing = db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_type == a_type,
            Artifact.title == a_title,
        ).first()
        if existing:
            existing.content = a_content
            existing.sources = [{"url": s} for s in art.get("sources", []) if isinstance(s, str)]
        else:
            db.add(Artifact(
                project_id=project_id,
                artifact_type=a_type,
                title=a_title,
                content=a_content,
                sources=[{"url": s} for s in art.get("sources", []) if isinstance(s, str)],
            ))
    db.flush()


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


def _strip_xml_tag(text: str, tag: str) -> str:
    """Strip an XML tag and its contents from text."""
    import re
    return re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL).strip()


def _extract_signals(messages: list[dict], latest_message: str, existing_signals: dict) -> dict:
    """LLM call #1: extract structured signals from the conversation.

    Uses mini model for speed — this is structured extraction, not creative generation.
    Strips <analysis> CoT reasoning before parsing JSON.
    """
    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:])
    prompt = SIGNAL_EXTRACTION_PROMPT.format(
        conversation=conversation,
        latest_message=latest_message,
        existing_signals=json.dumps(existing_signals),
    )
    raw = chat(prompt, model=MODEL_MINI)
    cleaned = _strip_xml_tag(raw, "analysis")
    return parse_json(cleaned)


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
    """LLM call #2: generate a response for the chosen action.

    Uses chat_messages() to pass base_prompt as system prompt and conversation
    history as actual message turns, so the LLM sees proper role structure.
    The action-specific instruction is appended as the final user message.
    """
    signals_str = json.dumps(signals, indent=2)
    open_questions = "\n".join(f"- {q}" for q in signals.get("open_questions", [])) or "None identified"

    if action == "ask_question":
        instruction = ASK_QUESTION_PROMPT.format(
            signals=signals_str,
            open_questions=open_questions,
        )
    elif action == "propose_plan":
        instruction = PROPOSE_PLAN_PROMPT.format(
            signals=signals_str,
        )
    elif action == "escalate":
        instruction = ESCALATE_PROMPT.format(
            signals=signals_str,
        )
    else:
        raise ValueError(f"Unknown action: {action}")

    # Build message list: conversation history + instruction as final user message.
    # If last message is user role, merge instruction into it to avoid consecutive
    # user messages (which OpenAI rejects).
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]
    if llm_messages and llm_messages[-1]["role"] == "user":
        llm_messages[-1] = {
            "role": "user",
            "content": llm_messages[-1]["content"] + "\n\n---\n\n" + instruction,
        }
    else:
        llm_messages.append({"role": "user", "content": instruction})

    raw = chat_messages(base_prompt, llm_messages, json_mode=True)
    return parse_json(raw)


def _handle_greeting(project, messages, recent_runs, base_prompt, db) -> dict:
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
        greeting_instruction = "Greet them briefly and ask what they'd like help with. Don't present generic options — start a real conversation."

    # Don't mention the default "New task" name — it's meaningless
    display_name = project.name if project.name.lower() not in ("new task", "untitled") else "this new task"
    instruction = GREETING_PROMPT.format(
        run_context=run_context,
        project_name=display_name,
        greeting_instruction=greeting_instruction,
    )

    # Pass any existing conversation as message history, instruction as final user message
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]
    llm_messages.append({"role": "user", "content": instruction})

    try:
        raw = chat_messages(base_prompt, llm_messages, json_mode=True)
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
        raw = chat(prompt, model=MODEL_JSON)  # Use gpt-4o for reliable JSON
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Synthesis LLM call failed: {e}")
        # Fallback: put the raw output into an artifact (right panel) instead of dumping it into chat
        raw_output = run.result_summary or ""
        # Extract a brief first line/sentence for the chat summary
        first_line = raw_output.split("\n")[0].strip() if raw_output else "The task completed."
        result = {
            "summary": f"{first_line}\n\nI've put the full findings on the right — take a look and let me know what direction you'd like to go.",
            "artifacts": [{
                "type": "report",
                "title": f"{project.name} — Research",
                "content": {"markdown": raw_output},
                "sources": [],
            }] if raw_output else [],
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


def mediate_regenerate(project_id: int, research_topic: str, research_text: str, db: Session) -> dict:
    """Re-run generation step with research context injected. Skips signal extraction."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Home chat gets its own regeneration
    if project and project.domain == "home":
        from backend.services.home import home_chat_regenerate
        return home_chat_regenerate(project_id, research_topic, research_text, db)

    project, user, recent, _ = _load_context(project_id, db)
    messages = [{"role": m.role, "content": m.content} for m in recent]
    base_prompt = build_system_prompt(user, project)

    context_text = get_context_text(db, user.id, project_id=project_id)
    if context_text:
        base_prompt += f"\n\n{context_text}"

    memory = retrieve_insights(user.id, project.description or "", db)
    if memory:
        base_prompt += f"\n\n{memory}"

    # Inject research context — tell the LLM the full details are in the workspace
    base_prompt += (
        f"\n\n## Research Results (displayed in the workspace panel on the right)\n"
        f"Topic: {research_topic}\n\n"
        f"The following research has been completed and is ALREADY VISIBLE to the user "
        f"in the workspace panel on the right side of their screen. Do NOT repeat these "
        f"details in your chat message. Instead, briefly reference what was found and "
        f"focus your chat message on the actionable next step or question.\n\n"
        f"{research_text[:3000]}"
    )

    existing_signals = project.conversation_signals or {}
    turn_count = sum(1 for m in messages if m["role"] == "user")
    action = _rank(existing_signals, turn_count, messages[-1]["content"] if messages else "")

    result = _generate(action, existing_signals, messages, base_prompt)
    result.setdefault("message", "")
    result.setdefault("actions", [])

    # Update the saved assistant message (replace the last one)
    last_msg = (
        db.query(ChatMessage)
        .filter_by(project_id=project_id, role="assistant")
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if last_msg:
        last_msg.content = result["message"]
        last_msg.actions = result.get("actions", [])
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
