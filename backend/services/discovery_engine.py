"""Agency Discovery Engine: domain-based elicitation to identify how AI agents can help.

Flow:
1. User selects life domains (work, health, hobbies, etc.)
2. System explores one domain at a time via structured conversation
3. Each domain uses a narrowing schema: context → friction → opportunity → metric
4. Produces concrete project proposals with success metrics
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import DiscoveryDomain, UserProfile, Project, get_session_factory
from backend.services.llm import chat, chat_json

logger = logging.getLogger(__name__)


# ── Domain Schemas ──────────────────────────────────────────────────

METRIC_STEP = {
    "id": "metric",
    "question_focus": "what does verifiable progress look like",
    "examples": ["weekly hours saved", "consistency streak", "items completed", "dollars saved"],
}

DOMAIN_SCHEMAS = {
    "work": {
        "label": "Work & Professional",
        "narrowing_steps": [
            {"id": "role", "question_focus": "role and work context", "examples": ["individual contributor", "manager", "freelancer", "business owner"]},
            {"id": "friction", "question_focus": "where time and energy is wasted", "examples": ["email overload", "manual reporting", "scattered research", "meeting prep"]},
            {"id": "tools", "question_focus": "current tools and workflows", "examples": ["Slack", "GitHub", "Salesforce", "Google Docs"]},
            {"id": "opportunity", "question_focus": "what AI agents could automate or augment"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["web research", "document drafting", "data analysis", "scheduling", "CRM automation", "email triage"],
    },
    "social": {
        "label": "Social Life & Relationships",
        "narrowing_steps": [
            {"id": "network", "question_focus": "important relationships and social goals", "examples": ["staying in touch with friends", "networking", "family coordination"]},
            {"id": "friction", "question_focus": "what makes social life feel like a chore", "examples": ["coordination fatigue", "forgetting birthdays", "running out of ideas"]},
            {"id": "opportunity", "question_focus": "what AI agents could coordinate or plan"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["event planning", "gift research", "scheduling coordination", "local event discovery"],
    },
    "studies": {
        "label": "Studies & Learning",
        "narrowing_steps": [
            {"id": "objective", "question_focus": "what they want to learn and why", "examples": ["specific skill", "broad field", "certification", "curiosity"]},
            {"id": "baseline", "question_focus": "current knowledge level and available time", "examples": ["complete beginner", "some experience", "2 hours/week"]},
            {"id": "friction", "question_focus": "what blocks learning progress", "examples": ["overwhelm", "no structure", "can't find good resources"]},
            {"id": "opportunity", "question_focus": "how AI agents could scaffold learning"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["curriculum design", "resource curation", "flashcard generation", "practice problem creation", "progress tracking"],
    },
    "health": {
        "label": "Health & Wellness",
        "narrowing_steps": [
            {"id": "focus", "question_focus": "health area of interest", "examples": ["sleep", "nutrition", "exercise", "stress", "specific condition"]},
            {"id": "friction", "question_focus": "what blocks consistency", "examples": ["no plan", "no accountability", "information overload", "motivation"]},
            {"id": "constraints", "question_focus": "limitations and preferences", "examples": ["injury", "time", "dietary restrictions", "budget"]},
            {"id": "opportunity", "question_focus": "what AI agents could track, plan, or research"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["habit tracking", "meal planning", "workout programming", "research synthesis", "supplement/nutrition research"],
    },
    "hobbies": {
        "label": "Hobbies & Projects",
        "narrowing_steps": [
            {"id": "archetype", "question_focus": "type of hobby or project", "examples": ["artistic", "technical", "collecting", "DIY", "outdoor"]},
            {"id": "tedium", "question_focus": "what parts feel like work rather than fun", "examples": ["supply sourcing", "organizing", "research", "admin"]},
            {"id": "vision", "question_focus": "what the ideal outcome or end goal looks like"},
            {"id": "opportunity", "question_focus": "what AI agents could handle without taking the fun away"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["supply sourcing", "tutorial curation", "scheduling practice", "reference gathering", "community finding"],
    },
    "money": {
        "label": "Money & Finances",
        "narrowing_steps": [
            {"id": "situation", "question_focus": "financial context and goals", "examples": ["saving for purchase", "debt reduction", "investing", "budgeting"]},
            {"id": "friction", "question_focus": "what makes finances feel overwhelming", "examples": ["tracking expenses", "comparing options", "tax prep", "no visibility"]},
            {"id": "opportunity", "question_focus": "what AI agents could automate or research"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["expense categorization", "deal finding", "subscription audit", "investment research", "budget tracking"],
    },
    "mental_health": {
        "label": "Mental Health & Resilience",
        "narrowing_steps": [
            {"id": "context", "question_focus": "current emotional landscape", "examples": ["stress", "burnout", "anxiety", "life transition", "motivation"]},
            {"id": "friction", "question_focus": "what makes it hard to maintain wellbeing", "examples": ["no routine", "isolation", "imposter syndrome", "overwhelm"]},
            {"id": "opportunity", "question_focus": "what supportive systems would help"},
            METRIC_STEP,
        ],
        "agent_capabilities": ["journaling prompts", "routine building", "resource finding", "habit nudges", "mood tracking"],
    },
}

DOMAIN_OPTIONS = [
    {"id": "work", "label": "Work & career", "icon": "briefcase"},
    {"id": "social", "label": "Social life", "icon": "users"},
    {"id": "studies", "label": "Studies & learning", "icon": "book"},
    {"id": "health", "label": "Health & wellness", "icon": "heart"},
    {"id": "hobbies", "label": "Hobbies & projects", "icon": "palette"},
    {"id": "money", "label": "Money & finances", "icon": "dollar"},
    {"id": "mental_health", "label": "Mental health", "icon": "brain"},
]


# ── Prompts ─────────────────────────────────────────────────────────

ELICITATION_PROMPT = """\
You are Liminal, having a collaborative conversation to understand how you can help \
{user_name} with their {domain_label}.

## Your approach
- Be constructive and mixed-initiative: share observations and hypotheses, don't just ask questions
- When you have enough context, reflect back what you're hearing: "It sounds like X is taking a lot of your energy. What if we..."
- Be specific, not generic. Reference what they've told you.
- Keep responses concise (2-4 sentences + question/reflection)

## Domain context
{domain_label} — typical areas where AI agents help: {capabilities}

## Current narrowing focus
We're exploring: **{step_focus}**
{step_examples}

## What we know so far
{signals_text}

## Conversation
{conversation_text}

## Your task
Generate the next message in this conversation. You should:
1. Acknowledge or build on what the user just said
2. Share a relevant observation or hypothesis about how AI could help
3. Ask a focused question about {step_focus}

When you present choices, include them as actions (clickable buttons).

Respond with JSON:
{{"message": "your message", "actions": [{{"label": "Short label", "description": "What this means", "action_text": "Reply text"}}]}}

Return ONLY the JSON object."""

SIGNAL_EXTRACTION_PROMPT = """\
Extract structured signals from this conversation about {domain_label}.

Conversation:
{conversation_text}

Latest message: {latest_message}

Existing signals: {existing_signals}

Return a JSON object that MERGES with existing signals. Include:
- "context": string — their situation/role/background for this domain
- "frictions": list of strings — specific pain points or time sinks
- "goals": list of strings — what they want to achieve
- "tools_used": list of strings — current tools/methods
- "opportunities": list of strings — where AI agents could help
- "metric_candidates": list of strings — potential success metrics identified
- "selected_metric": string or null — if they've agreed on a metric
- "metric_target": string or null — target value for the metric

IMPORTANT: Remove answered items, don't re-add what's already captured.
Return ONLY the JSON object."""

PROJECT_PROPOSAL_PROMPT = """\
Based on the discovery conversation about {domain_label} with {user_name}, propose 1-3 concrete projects.

## What we learned
{signals_text}

## Conversation
{conversation_text}

Each project should:
- Be a BROAD, ongoing project (not a single task)
- Have a clear name and description
- Include a first_goal: the very first thing the AI agent would do
- Include success_metric and metric_target based on what was discussed

Respond with a JSON array:
[{{"name": "Project name", "description": "What the AI will do", "first_goal": "First concrete task", "success_metric": "metric name", "metric_target": "target value"}}]

Return ONLY the JSON array."""

OPENING_PROMPT = """\
You are Liminal, starting a discovery conversation with {user_name} about {domain_label}.

This is the first message in the conversation. You should:
1. Acknowledge that they want more agency in this area
2. Share what kinds of things AI agents can typically help with here: {capabilities}
3. Ask a warm, specific opening question about their situation

Keep it to 2-3 sentences. Be conversational, not clinical.

Respond with JSON:
{{"message": "your opening message", "actions": [{{"label": "Short label", "description": "What this means", "action_text": "Reply text"}}]}}

Return ONLY the JSON object."""


# ── Engine ──────────────────────────────────────────────────────────

class DiscoveryEngine:
    """Drives domain-based agency discovery conversations."""

    def select_domains(self, user_id: str, domains: list[str], db: Session) -> dict:
        """Record selected domains and return the opening message for the first one."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        user.selected_domains = list(domains)

        # Create DiscoveryDomain records
        for i, domain in enumerate(domains):
            if domain not in DOMAIN_SCHEMAS:
                continue
            dd = DiscoveryDomain(
                user_id=user_id,
                domain=domain,
                status="active" if i == 0 else "pending",
            )
            db.add(dd)

        db.commit()

        # Generate opening for first domain
        first_domain = domains[0] if domains else None
        if not first_domain or first_domain not in DOMAIN_SCHEMAS:
            return {"message": "Let's get started! What area would you like to explore first?", "actions": [], "domain": None}

        schema = DOMAIN_SCHEMAS[first_domain]
        return self._generate_opening(user, first_domain, schema, db)

    def get_state(self, user_id: str, db: Session) -> dict:
        """Return current discovery state for the user."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        domains = db.query(DiscoveryDomain).filter_by(user_id=user_id).order_by(DiscoveryDomain.created_at).all()
        active = next((d for d in domains if d.status == "active"), None)

        return {
            "selected_domains": user.selected_domains or [],
            "discovery_complete": user.discovery_complete,
            "domains": [
                {
                    "domain": d.domain,
                    "label": DOMAIN_SCHEMAS.get(d.domain, {}).get("label", d.domain),
                    "status": d.status,
                    "depth": d.depth,
                    "conversation": d.conversation or [],
                    "proposed_projects": d.proposed_projects or [],
                }
                for d in domains
            ],
            "active_domain": active.domain if active else None,
        }

    def process_response(self, user_id: str, message: str, db: Session) -> dict:
        """Process a user response in the active domain conversation."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").first()
        if not active:
            return {"message": "No active domain to explore. Select domains first.", "actions": [], "domain": None}

        schema = DOMAIN_SCHEMAS.get(active.domain)
        if not schema:
            return {"message": "Unknown domain.", "actions": [], "domain": active.domain}

        # Save user message to conversation
        conv = list(active.conversation or [])
        conv.append({"role": "user", "content": message})

        # Extract signals
        try:
            new_signals = self._extract_signals(active, schema, message, conv)
            merged = self._merge_signals(active.signals or {}, new_signals)
        except Exception as e:
            logger.warning(f"Signal extraction failed: {e}")
            merged = active.signals or {}

        active.signals = dict(merged)
        active.depth = (active.depth or 0) + 1
        active.conversation = conv
        db.flush()

        # Decide next action
        action = self._should_advance(active, schema)

        if action == "propose_projects":
            result = self._propose_projects(user, active, schema, conv, db)
        else:
            result = self._generate_next(user, active, schema, conv)

        # Save assistant message
        conv.append({"role": "assistant", "content": result["message"]})
        active.conversation = list(conv)
        db.commit()

        result["domain"] = active.domain
        result["depth"] = active.depth
        return result

    def accept_projects(self, user_id: str, project_indices: list[int], db: Session) -> list[dict]:
        """Create Projects from proposals and advance to next domain."""
        active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="explored").first()
        if not active:
            active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").first()
        if not active:
            raise ValueError("No domain with proposals to accept")

        proposals = active.proposed_projects or []
        created = []

        for idx in project_indices:
            if 0 <= idx < len(proposals):
                p = proposals[idx]
                project = Project(
                    user_id=user_id,
                    name=p.get("name", "New project"),
                    description=p.get("description", ""),
                    success_metric=p.get("success_metric"),
                    metric_target=p.get("metric_target"),
                    domain=active.domain,
                    suggested_by_system=True,
                )
                db.add(project)
                db.flush()
                created.append({
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "success_metric": project.success_metric,
                    "metric_target": project.metric_target,
                })

        active.status = "completed"
        db.flush()

        # Advance to next pending domain
        next_result = self._advance_to_next(user_id, db)
        db.commit()

        return {"created_projects": created, **next_result}

    def skip_domain(self, user_id: str, db: Session) -> dict:
        """Skip the current active domain."""
        active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").first()
        if active:
            active.status = "completed"
            db.flush()

        result = self._advance_to_next(user_id, db)
        db.commit()
        return result

    def complete_discovery(self, user_id: str, db: Session) -> dict:
        """Finalize discovery: mark complete, generate user model summary."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        user.discovery_complete = True
        user.onboarding_complete = True

        # Aggregate all domain signals into user model
        domains = db.query(DiscoveryDomain).filter_by(user_id=user_id).all()
        all_signals = {}
        for d in domains:
            if d.signals:
                all_signals[d.domain] = d.signals

        # Generate model summary
        try:
            user.model_summary = self._generate_model_summary(user.name, all_signals)
            user.onboarding_info = json.dumps(all_signals)
        except Exception as e:
            logger.warning(f"Model summary generation failed: {e}")

        db.commit()
        return {"status": "complete", "model_summary": user.model_summary}

    # ── Internal helpers ────────────────────────────────────────────

    def _generate_opening(self, user: UserProfile, domain: str, schema: dict, db: Session) -> dict:
        """Generate the opening message for a domain conversation."""
        prompt = OPENING_PROMPT.format(
            user_name=user.name,
            domain_label=schema["label"],
            capabilities=", ".join(schema["agent_capabilities"]),
        )
        try:
            result = chat_json(prompt)
        except Exception as e:
            logger.warning(f"Opening generation failed: {e}")
            result = {
                "message": f"Let's explore how I can help with your {schema['label'].lower()}. Tell me a bit about your situation — what's going on in this area of your life?",
                "actions": [],
            }

        # Save to conversation
        active = db.query(DiscoveryDomain).filter_by(user_id=user.id, domain=domain, status="active").first()
        if active:
            active.conversation = [{"role": "assistant", "content": result.get("message", "")}]
            db.flush()

        result.setdefault("actions", [])
        result["domain"] = domain
        return result

    def _extract_signals(self, domain: DiscoveryDomain, schema: dict, message: str, conv: list) -> dict:
        """LLM call to extract structured signals from the conversation."""
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        prompt = SIGNAL_EXTRACTION_PROMPT.format(
            domain_label=schema["label"],
            conversation_text=conv_text,
            latest_message=message,
            existing_signals=json.dumps(domain.signals or {}),
        )
        return chat_json(prompt)

    def _merge_signals(self, existing: dict, new: dict) -> dict:
        """Merge new signals into existing, deduplicating lists."""
        merged = {**existing}
        for key, value in new.items():
            if isinstance(value, list) and isinstance(merged.get(key), list):
                seen = set()
                deduped = []
                for item in merged[key] + value:
                    item_key = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
                    if item_key not in seen:
                        seen.add(item_key)
                        deduped.append(item)
                merged[key] = deduped
            elif value is not None:
                merged[key] = value
        return merged

    def _should_advance(self, domain: DiscoveryDomain, schema: dict) -> str:
        """Rule-based: decide whether to keep asking or propose projects."""
        steps = schema["narrowing_steps"]
        depth = domain.depth or 0
        signals = domain.signals or {}

        # If we've been through all narrowing steps, propose
        if depth >= len(steps):
            return "propose_projects"

        # If we have good signals and a metric, propose early
        has_opportunities = bool(signals.get("opportunities"))
        has_metric = bool(signals.get("selected_metric"))
        if has_opportunities and has_metric and depth >= 3:
            return "propose_projects"

        # After 6 turns, propose regardless
        if depth >= 6:
            return "propose_projects"

        return "ask_more"

    def _generate_next(self, user: UserProfile, domain: DiscoveryDomain, schema: dict, conv: list) -> dict:
        """Generate the next conversational message."""
        steps = schema["narrowing_steps"]
        current_step_idx = min(domain.depth or 0, len(steps) - 1)
        step = steps[current_step_idx]

        signals_text = json.dumps(domain.signals or {}, indent=2) if domain.signals else "Nothing yet"
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        step_examples = f"Examples: {', '.join(step.get('examples', []))}" if step.get("examples") else ""

        prompt = ELICITATION_PROMPT.format(
            user_name=user.name,
            domain_label=schema["label"],
            capabilities=", ".join(schema["agent_capabilities"]),
            step_focus=step["question_focus"],
            step_examples=step_examples,
            signals_text=signals_text,
            conversation_text=conv_text,
        )

        try:
            result = chat_json(prompt)
        except Exception as e:
            logger.warning(f"Elicitation generation failed: {e}")
            result = {"message": f"Tell me more about {step['question_focus']}.", "actions": []}

        result.setdefault("actions", [])
        return result

    def _propose_projects(self, user: UserProfile, domain: DiscoveryDomain, schema: dict, conv: list, db: Session) -> dict:
        """Generate project proposals from accumulated signals."""
        signals_text = json.dumps(domain.signals or {}, indent=2)
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])

        prompt = PROJECT_PROPOSAL_PROMPT.format(
            domain_label=schema["label"],
            user_name=user.name,
            signals_text=signals_text,
            conversation_text=conv_text,
        )

        try:
            proposals = chat_json(prompt)
            if not isinstance(proposals, list):
                proposals = [proposals]
        except Exception as e:
            logger.warning(f"Project proposal generation failed: {e}")
            proposals = [{
                "name": f"{schema['label']} Assistant",
                "description": f"Help with {schema['label'].lower()} based on our conversation.",
                "first_goal": "Get started with initial research and planning.",
                "success_metric": (domain.signals or {}).get("selected_metric", "tasks completed"),
                "metric_target": (domain.signals or {}).get("metric_target", "weekly"),
            }]

        domain.proposed_projects = list(proposals)
        domain.status = "explored"
        db.flush()

        # Format as a message with accept buttons
        proposal_text = "Based on our conversation, here are some projects I could set up for you:\n\n"
        actions = []
        for i, p in enumerate(proposals):
            proposal_text += f"**{i+1}. {p['name']}**\n{p['description']}\n"
            if p.get("success_metric"):
                proposal_text += f"📊 Success metric: {p['success_metric']}"
                if p.get("metric_target"):
                    proposal_text += f" (target: {p['metric_target']})"
                proposal_text += "\n"
            proposal_text += f"First step: {p.get('first_goal', 'Get started')}\n\n"
            actions.append({
                "label": f"Add: {p['name'][:30]}",
                "description": p["description"][:80],
                "action_text": f"accept_project:{i}",
            })

        actions.append({
            "label": "Accept all",
            "description": "Add all proposed projects",
            "action_text": "accept_all",
        })
        actions.append({
            "label": "Skip this domain",
            "description": "Move to the next area",
            "action_text": "skip_domain",
        })

        return {"message": proposal_text, "actions": actions, "proposed_projects": proposals}

    def _advance_to_next(self, user_id: str, db: Session) -> dict:
        """Activate the next pending domain or signal completion."""
        next_domain = db.query(DiscoveryDomain).filter_by(
            user_id=user_id, status="pending"
        ).order_by(DiscoveryDomain.created_at).first()

        if next_domain:
            next_domain.status = "active"
            db.flush()
            user = db.query(UserProfile).filter_by(id=user_id).first()
            schema = DOMAIN_SCHEMAS.get(next_domain.domain, {})
            opening = self._generate_opening(user, next_domain.domain, schema, db)
            return {"next_domain": next_domain.domain, "opening": opening, "all_complete": False}
        else:
            return {"next_domain": None, "opening": None, "all_complete": True}

    def _generate_model_summary(self, name: str, all_signals: dict) -> str:
        """Generate a user model summary from all domain signals."""
        prompt = f"""Write a concise profile summary (3-5 sentences) of {name} based on their agency discovery conversations.

Domain signals:
{json.dumps(all_signals, indent=2)}

Focus on: who they are, what they need help with, what their goals are, and their preferred metrics for success. Write in third person. Return ONLY the summary text."""

        return chat(prompt)


discovery_engine = DiscoveryEngine()
