"""Home chat service: ongoing conversation focused on understanding the user.

No plan/escalate pipeline. Just conversational flow with cross-domain synthesis
and navigation suggestions when appropriate.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import (
    ChatMessage, Project, UserProfile, DiscoveryDomain,
)
from backend.services.llm import chat_messages, parse_json
from backend.services.prompt_builder import build_system_prompt
from backend.services.context_service import get_context_text
from backend.prompts.home import (
    HOME_GREETING_PROMPT, HOME_CONVERSATION_PROMPT,
    HOME_ROUTING_CHECK, HOME_NAVIGATION_PROMPT,
)
from backend.services.memory import extract_insights, retrieve_insights

logger = logging.getLogger(__name__)


def home_chat(project_id: int, user_message: Optional[str], db: Session) -> dict:
    """Process a message in the Home chat (extract + generate).

    Returns dict with keys: message, actions, escalate (always False), task_description (always "")
    """
    extract_result = home_chat_extract(project_id, user_message, db)

    if extract_result.get("_early_return"):
        result = extract_result
        result.pop("_early_return", None)
        return result

    return home_chat_generate(extract_result, db)


def home_chat_extract(project_id: int, user_message: Optional[str], db: Session) -> dict:
    """Extract phase for home chat: signals + context. Returns intermediate state.

    Returns dict with _extract_state or _early_return=True for greetings.
    """
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    user = db.query(UserProfile).filter_by(id=project.user_id).first()
    if not user:
        raise ValueError(f"User not found for project {project_id}")

    # Load recent messages
    recent = (
        db.query(ChatMessage)
        .filter_by(project_id=project_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    recent.reverse()
    messages = [{"role": m.role, "content": m.content} for m in recent]

    # Build base system prompt
    base_prompt = build_system_prompt(user, project)

    # Build shared context blocks
    domain_context = _build_domain_context(user, db)
    memory_context = retrieve_insights(user.id, user_message or "", db)
    model_summary = memory_context if memory_context else (
        f"What we know: {user.model_summary}" if user.model_summary else "New user — we don't know much yet."
    )

    # Inject user-uploaded context
    uploaded = get_context_text(db, user.id, project_id=project_id)
    if uploaded:
        base_prompt += f"\n\n{uploaded}"

    # Greeting (no user message)
    if not user_message:
        if any(m["role"] == "assistant" for m in messages):
            last = next(m for m in reversed(messages) if m["role"] == "assistant")
            return {"message": last["content"], "actions": [], "escalate": False, "task_description": "", "_early_return": True}
        result = _greeting(user, project, messages, base_prompt, domain_context, model_summary, db)
        result["_early_return"] = True
        return result

    # Save user message
    db.add(ChatMessage(project_id=project_id, role="user", content=user_message))
    db.commit()
    messages.append({"role": "user", "content": user_message})

    # Extract and accumulate conversation signals (uses mini model, fast)
    # Note: research detection happens in generate phase (gpt-4o), not here
    existing_signals = project.conversation_signals or {}
    try:
        from backend.services.mediator import _extract_signals, _merge_signals
        new_signals = _extract_signals(messages, user_message, existing_signals)
        merged = _merge_signals(existing_signals, new_signals)
        project.conversation_signals = dict(merged)
        db.flush()
    except Exception as e:
        logger.warning(f"Home signal extraction failed: {e}")

    signals = _summarize_known(user, project, db)
    project_context = _build_project_context(user, db, project_id)

    return {
        "_extract_state": {
            "messages": messages,
            "base_prompt": base_prompt,
            "project_id": project_id,
            "user_id": user.id,
            "user_name": user.name,
            "user_message": user_message,
            "model_summary": model_summary,
            "domain_context": domain_context,
            "project_context": project_context,
            "signals": signals,
        },
    }


def home_chat_generate(extract_result: dict, db: Session) -> dict:
    """Generate phase for home chat: produce response from extracted state.

    Takes the output of home_chat_extract (must have _extract_state key).
    Uses routing check to decide between curiosity (get to know) vs navigation.
    """
    state = extract_result["_extract_state"]
    messages = state["messages"]
    base_prompt = state["base_prompt"]
    project_id = state["project_id"]
    user_id = state["user_id"]
    user_message = state["user_message"]

    # Step 1: Check if we should suggest navigation (fast mini model)
    nav_suggestion = _check_navigation(messages, state["domain_context"], db, user_id=user_id)

    if nav_suggestion:
        # Use navigation prompt
        domain_id = nav_suggestion["domain"]
        domain_label = _get_domain_label(domain_id)
        instruction = HOME_NAVIGATION_PROMPT.format(
            user_name=state["user_name"],
            domain_label=domain_label,
            domain_id=domain_id,
        )
    else:
        # Use curiosity prompt (get to know them)
        instruction = HOME_CONVERSATION_PROMPT.format(
            user_name=state["user_name"],
            model_summary=state["model_summary"],
            signals=state["signals"],
        )

    # Build message list for LLM
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]
    if llm_messages and llm_messages[-1]["role"] == "user":
        llm_messages[-1] = {
            "role": "user",
            "content": llm_messages[-1]["content"] + "\n\n---\n\n" + instruction,
        }
    else:
        llm_messages.append({"role": "user", "content": instruction})

    try:
        raw = chat_messages(base_prompt, llm_messages, json_mode=True)
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Home chat generation failed: {e}")
        result = {
            "message": "Tell me more about that — I'm curious.",
            "actions": [],
        }

    result.setdefault("message", "")
    result.setdefault("actions", [])
    result["escalate"] = False
    result["task_description"] = ""
    # Keep research field — router will check it if extract phase missed it

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
        extract_insights(user_id, user_message, result["message"], "home", str(project_id), db)

    return result


def _check_navigation(messages: list[dict], domain_context: str, db: Session, user_id: str = None) -> Optional[dict]:
    """Check if we should suggest navigation to a domain. Uses fast mini model."""
    from backend.services.llm import chat as llm_chat, MODEL_MINI

    # Need at least 4 messages (2 turns) to consider navigation
    if len(messages) < 4:
        return None

    # Get user's actual selected domains from DB (not hardcoded list)
    if user_id:
        user_domains = db.query(DiscoveryDomain).filter_by(user_id=user_id).all()
        domain_ids = [d.domain for d in user_domains]
        if not domain_ids:
            return None  # User hasn't selected any domains
        available = ", ".join(domain_ids)
    else:
        return None  # Can't check without user_id

    # Build conversation summary (last 6 messages)
    recent = messages[-6:]
    summary = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in recent)

    prompt = HOME_ROUTING_CHECK.format(
        conversation_summary=summary,
        available_domains=available,
    )

    try:
        raw = llm_chat(prompt, model=MODEL_MINI)
        result = parse_json(raw)
        if result.get("suggest_navigation") and result.get("domain"):
            logger.debug(f"Navigation check: suggest {result['domain']} - {result.get('reason')}")
            return result
    except Exception as e:
        logger.debug(f"Navigation check failed: {e}")

    return None


def _get_domain_label(domain_id: str) -> str:
    """Get human-readable label for a domain."""
    labels = {
        "work": "Work & Career",
        "social": "Social Life",
        "studies": "Studies & Learning",
        "health": "Health & Wellness",
        "hobbies": "Hobbies & Projects",
        "money": "Money & Finances",
        "mental_health": "Mind & Mental Health",
    }
    return labels.get(domain_id, domain_id.replace("_", " ").title())


def home_chat_regenerate(project_id: int, research_topic: str, research_text: str, db: Session) -> dict:
    """Re-run home chat generation with research context. Skips signal extraction."""
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
    messages = [{"role": m.role, "content": m.content} for m in recent]

    base_prompt = build_system_prompt(user, project)
    domain_context = _build_domain_context(user, db)
    last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    memory_context = retrieve_insights(user.id, last_user_msg, db)
    model_summary = memory_context if memory_context else (
        f"What we know: {user.model_summary}" if user.model_summary else "New user — we don't know much yet."
    )

    uploaded = get_context_text(db, user.id, project_id=project_id)
    if uploaded:
        base_prompt += f"\n\n{uploaded}"

    signals = _summarize_known(user, project, db)
    project_context = _build_project_context(user, db, project_id)

    instruction = HOME_CONVERSATION_PROMPT.format(
        user_name=user.name,
        model_summary=model_summary,
        domain_context=domain_context,
        project_context=project_context,
        signals=signals,
    )

    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]
    if llm_messages and llm_messages[-1]["role"] == "user":
        llm_messages[-1] = {
            "role": "user",
            "content": llm_messages[-1]["content"] + "\n\n---\n\n" + instruction,
        }
    else:
        llm_messages.append({"role": "user", "content": instruction})

    try:
        raw = chat_messages(base_prompt, llm_messages, json_mode=True)
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Home chat regeneration failed: {e}")
        result = {"message": "Tell me more about that — I'm curious.", "actions": []}

    result.setdefault("message", "")
    result.setdefault("actions", [])

    # Update the last assistant message with regenerated content
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


def _greeting(user, project, messages, base_prompt, domain_context, model_summary, db) -> dict:
    """Generate a home greeting."""
    instruction = HOME_GREETING_PROMPT.format(
        user_name=user.name,
        model_summary=model_summary,
        domain_context=domain_context,
    )

    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]
    llm_messages.append({"role": "user", "content": instruction})

    try:
        raw = chat_messages(base_prompt, llm_messages, json_mode=True)
        result = parse_json(raw)
    except Exception as e:
        logger.warning(f"Home greeting failed: {e}")
        result = {
            "message": f"Hey {user.name}! I'd love to get to know you — tell me a bit about yourself.",
            "actions": [],
        }

    result.setdefault("message", "")
    result.setdefault("actions", [])
    result["escalate"] = False
    result["task_description"] = ""

    db.add(ChatMessage(
        project_id=project.id,
        role="assistant",
        content=result["message"],
        actions=result["actions"],
    ))
    db.commit()

    return result


def _build_domain_context(user: UserProfile, db: Session) -> str:
    """Build a summary of what we know from discovery domains."""
    domains = db.query(DiscoveryDomain).filter_by(user_id=user.id).all()
    active_with_signals = [d for d in domains if d.signals and d.depth > 0]

    if active_with_signals:
        parts = ["## What I Know About You (From Discovery)"]
        for d in active_with_signals:
            label = (d.schema or {}).get("label", d.domain) if d.schema else d.domain
            parts.append(f"\n### {label}")
            parts.append(json.dumps(d.signals, indent=2))
        return "\n".join(parts)

    # No discovery conversations yet — list available domains so the LLM can suggest them
    from backend.services.discovery_engine import DOMAIN_OPTIONS
    active_ids = {d.domain for d in domains}
    parts = ["## Domain context"]
    if active_ids:
        parts.append(f"Active domains (selected but not yet explored): {', '.join(active_ids)}")
    else:
        parts.append("No domains set up yet.")
    parts.append(f"Available domains: {', '.join(d['id'] + ' (' + d['label'] + ')' for d in DOMAIN_OPTIONS)}")
    return "\n".join(parts)


def _build_project_context(user: UserProfile, db: Session, exclude_project_id: int) -> str:
    """Build a summary of existing projects for navigation suggestions."""
    projects = (
        db.query(Project)
        .filter_by(user_id=user.id)
        .filter(Project.id != exclude_project_id)
        .filter(Project.status == "active")
        .all()
    )
    if not projects:
        return "No other active projects."

    parts = ["## Existing Projects"]
    for p in projects:
        parts.append(f"- **{p.name}** (id={p.id}): {p.description[:100]}")

    return "\n".join(parts)


def _summarize_known(user: UserProfile, project: Project, db: Session) -> str:
    """Summarize what we know from conversation signals without an LLM call."""
    signals = project.conversation_signals or {}
    if not signals:
        return "Nothing accumulated yet in this conversation."

    parts = []
    for key in ("intent", "needs", "goals", "constraints"):
        val = signals.get(key)
        if val:
            if isinstance(val, list):
                parts.append(f"- {key}: {', '.join(str(v) for v in val)}")
            else:
                parts.append(f"- {key}: {val}")

    return "\n".join(parts) if parts else "Nothing accumulated yet in this conversation."
