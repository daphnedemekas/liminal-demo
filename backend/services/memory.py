"""Memory service: extract and retrieve user insights across all chat layers."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import Insight, get_session_factory
from backend.services.llm import chat_json

logger = logging.getLogger(__name__)


INSIGHT_EXTRACTION_PROMPT = """\
Extract factual insights about the user from this conversation exchange.

User message: {user_message}
Assistant response: {assistant_response}

Existing insights (do NOT repeat these):
{existing_insights}

Return a JSON array of NEW insights only. Each insight:
{{"category": "bio|preference|goal|friction|value|fact|decision", "content": "concise factual statement", "keywords": "comma,separated,keywords", "confidence": "stated|inferred"}}

Categories:
- bio: biographical facts (location, job, family, age, background)
- preference: how they like things, communication style, tools they prefer
- goal: something they want to achieve
- friction: something that frustrates or blocks them
- value: what they care about, what motivates them
- fact: specific detail (company name, tech stack, hobby specifics)
- decision: a decision they've made

Rules:
- Only extract NEW insights not already captured above
- "stated" = user said it directly. "inferred" = reading between the lines
- Be concise: "Lives in Austin" not "The user mentioned they live in Austin, TX"
- Skip trivial/transient things ("I'm tired today", "thanks")
- Return [] if nothing worth extracting

Return ONLY the JSON array."""


def _do_extract(
    user_id: str,
    user_message: str,
    assistant_response: str,
    source_layer: str,
    source_id: Optional[str],
    existing_text: str,
) -> None:
    """Run insight extraction in a background thread with its own DB session."""
    session = get_session_factory()()
    try:
        prompt = INSIGHT_EXTRACTION_PROMPT.format(
            user_message=user_message,
            assistant_response=assistant_response,
            existing_insights=existing_text,
        )

        from backend.services.llm import MODEL_MINI
        new_insights = chat_json(prompt, model=MODEL_MINI)
        if not isinstance(new_insights, list):
            return
        for ins in new_insights:
            content = ins.get("content", "").strip()
            if not content:
                continue
            session.add(Insight(
                user_id=user_id,
                source_layer=source_layer,
                source_id=str(source_id) if source_id else None,
                category=ins.get("category", "fact"),
                content=content,
                keywords=ins.get("keywords", ""),
                confidence=ins.get("confidence", "inferred"),
            ))
        session.commit()
    except Exception as e:
        logger.warning(f"Insight extraction failed: {e}")
        session.rollback()
    finally:
        session.close()


def extract_insights(
    user_id: str,
    user_message: str,
    assistant_response: str,
    source_layer: str,
    source_id: Optional[str],
    db: Session,
) -> None:
    """Extract and persist insights from a conversation turn (background thread)."""
    if not user_message or not user_message.strip():
        return

    # Read existing insights on the caller's session (fast, read-only)
    existing = (
        db.query(Insight)
        .filter_by(user_id=user_id)
        .filter(Insight.superseded_by.is_(None))
        .order_by(Insight.created_at.desc())
        .limit(50)
        .all()
    )
    existing_text = (
        "\n".join(f"- [{i.category}] {i.content}" for i in existing)
        or "None yet"
    )

    # Fire and forget in a background thread with its own session
    t = threading.Thread(
        target=_do_extract,
        args=(user_id, user_message, assistant_response, source_layer, source_id, existing_text),
        daemon=True,
    )
    t.start()


RESEARCH_INSIGHT_PROMPT = """\
Summarize the key facts from this research into concise insights.

Research topic: {topic}
Research results: {results}

Return a JSON array. Each insight:
{{"category": "fact", "content": "concise factual statement", "keywords": "comma,separated,keywords", "confidence": "stated"}}

Rules:
- Extract 2-5 key facts about the topic
- Be concise: "Softmax: AI alignment startup by Emmett Shear, backed by a16z"
- Include the most useful/relevant facts, skip minor details
- Return ONLY the JSON array."""


def _do_extract_research(
    user_id: str,
    topic: str,
    results: str,
    source_layer: str,
    source_id: Optional[str],
) -> None:
    """Run research insight extraction in a background thread with its own DB session."""
    session = get_session_factory()()
    try:
        prompt = RESEARCH_INSIGHT_PROMPT.format(topic=topic, results=results)
        from backend.services.llm import MODEL_MINI
        new_insights = chat_json(prompt, model=MODEL_MINI)
        if not isinstance(new_insights, list):
            return
        for ins in new_insights:
            content = ins.get("content", "").strip()
            if not content:
                continue
            session.add(Insight(
                user_id=user_id,
                source_layer=source_layer,
                source_id=str(source_id) if source_id else None,
                category=ins.get("category", "fact"),
                content=content,
                keywords=ins.get("keywords", ""),
                confidence=ins.get("confidence", "stated"),
            ))
        session.commit()
    except Exception as e:
        logger.warning(f"Research insight extraction failed: {e}")
        session.rollback()
    finally:
        session.close()


def extract_research_insights(
    user_id: str,
    topic: str,
    results: str,
    source_id: Optional[str],
    db: Session,
) -> None:
    """Extract and persist insights from research results (background thread)."""
    if not results or not results.strip():
        return
    t = threading.Thread(
        target=_do_extract_research,
        args=(user_id, topic, results, "research", source_id),
        daemon=True,
    )
    t.start()


def retrieve_insights(
    user_id: str,
    context: str,
    db: Session,
    limit: int = 15,
) -> str:
    """Retrieve relevant insights for prompt injection.

    Strategy: always include bio/value/preference + keyword match + recency.
    """
    all_insights = (
        db.query(Insight)
        .filter_by(user_id=user_id)
        .filter(Insight.superseded_by.is_(None))
        .order_by(Insight.created_at.desc())
        .all()
    )
    if not all_insights:
        return ""

    # Always include core identity insights
    always = [i for i in all_insights if i.category in ("bio", "value", "preference")]

    # Keyword match remaining against context
    context_words = set(context.lower().split()) if context else set()
    scored = []
    always_ids = {i.id for i in always}
    for i in all_insights:
        if i.id in always_ids:
            continue
        kw = set(k.strip() for k in i.keywords.lower().split(",")) if i.keywords else set()
        content_words = set(i.content.lower().split())
        overlap = len((kw | content_words) & context_words)
        if overlap > 0:
            scored.append((overlap, i))
    scored.sort(key=lambda x: -x[0])
    matched = [i for _, i in scored[: limit - len(always)]]

    # Fill remaining with most recent
    used_ids = {i.id for i in always + matched}
    remaining = max(0, limit - len(always) - len(matched))
    recents = [i for i in all_insights if i.id not in used_ids][:remaining]

    final = always + matched + recents
    if not final:
        return ""

    lines = ["## What I Remember About You"]
    for i in final:
        lines.append(f"- {i.content}")
    return "\n".join(lines)


def already_researched(user_id: str, topic: str, db: Session) -> bool:
    """Check if we already have research insights matching this topic."""
    if not topic:
        return False
    topic_words = set(topic.lower().split())
    # Check insights from research layer
    research_insights = (
        db.query(Insight)
        .filter_by(user_id=user_id, source_layer="research")
        .filter(Insight.superseded_by.is_(None))
        .all()
    )
    for ins in research_insights:
        kw = set(k.strip() for k in ins.keywords.lower().split(",")) if ins.keywords else set()
        content_words = set(ins.content.lower().split())
        overlap = len((kw | content_words) & topic_words)
        if overlap >= 2:
            return True
    return False
