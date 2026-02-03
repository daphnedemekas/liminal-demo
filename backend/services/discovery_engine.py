"""Agency Discovery Engine: domain-based elicitation to identify how AI agents can help.

Flow:
1. User selects life domains (work, health, hobbies, etc.)
2. LLM generates a personalized narrowing schema per domain
3. System explores one domain at a time via structured conversation
4. Each domain uses its generated schema: context → friction → opportunity → metric
5. Produces concrete project proposals with success metrics
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import ChatMessage, DiscoveryDomain, UserProfile, Project, get_session_factory
from backend.services.llm import chat, chat_json, chat_json_parallel, parse_json, MODEL_MINI, MODEL_JSON
from backend.services.context_service import get_context_text
from backend.prompts.domains import get_domain_prompts

logger = logging.getLogger(__name__)


def _format_proposals(proposals: list[dict], intro: str) -> tuple[str, list[dict]]:
    """Format project proposals into a readable message with action buttons."""
    text = f"{intro}\n\n"
    actions = []
    for i, p in enumerate(proposals):
        text += f"### {i+1}. {p['name']}\n"
        text += f"{p['description']}\n\n"
        if p.get("what_agent_does"):
            text += f"**What I'll do:** {p['what_agent_does']}\n"
        if p.get("what_user_does"):
            text += f"**What you'll do:** {p['what_user_does']}\n"
        if p.get("first_goal"):
            text += f"**First step:** {p['first_goal']}\n"
        if p.get("prerequisites"):
            text += f"**I'll need from you:** {p['prerequisites']}\n"
        if p.get("success_metric"):
            metric = p["success_metric"]
            if p.get("metric_target"):
                metric += f" — target: {p['metric_target']}"
            text += f"**Tracking:** {metric}\n"
        text += "\n---\n\n"
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
    return text, actions


# ── Metric step (appended to every generated schema) ────────────────

METRIC_STEP = {
    "id": "metric",
    "question_focus": "what does verifiable progress look like",
    "examples": ["weekly hours saved", "consistency streak", "items completed", "dollars saved"],
}


# ── Example schemas (used as format reference for LLM generation) ───

DOMAIN_SCHEMA_EXAMPLES = {
    "work": {
        "label": "Work & Professional",
        "narrowing_steps": [
            {"id": "role", "question_focus": "role and work context", "examples": ["individual contributor", "manager", "freelancer", "business owner"]},
            {"id": "friction", "question_focus": "where time and energy is wasted", "examples": ["email overload", "manual reporting", "scattered research", "meeting prep"]},
            {"id": "tools", "question_focus": "current tools and workflows", "examples": ["Slack", "GitHub", "Salesforce", "Google Docs"]},
            {"id": "opportunity", "question_focus": "what AI agents could automate or augment"},
        ],
        "agent_capabilities": ["web research", "document drafting", "data analysis", "scheduling", "CRM automation", "email triage"],
    },
    "social": {
        "label": "Social Life & Relationships",
        "narrowing_steps": [
            {"id": "network", "question_focus": "important relationships and social goals", "examples": ["staying in touch with friends", "networking", "family coordination"]},
            {"id": "friction", "question_focus": "what makes social life feel like a chore", "examples": ["coordination fatigue", "forgetting birthdays", "running out of ideas"]},
            {"id": "opportunity", "question_focus": "what AI agents could coordinate or plan"},
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
        ],
        "agent_capabilities": ["supply sourcing", "tutorial curation", "scheduling practice", "reference gathering", "community finding"],
    },
    "money": {
        "label": "Money & Finances",
        "narrowing_steps": [
            {"id": "situation", "question_focus": "financial context and goals", "examples": ["saving for purchase", "debt reduction", "investing", "budgeting"]},
            {"id": "friction", "question_focus": "what makes finances feel overwhelming", "examples": ["tracking expenses", "comparing options", "tax prep", "no visibility"]},
            {"id": "opportunity", "question_focus": "what AI agents could automate or research"},
        ],
        "agent_capabilities": ["expense categorization", "deal finding", "subscription audit", "investment research", "budget tracking"],
    },
    "mental_health": {
        "label": "Mind & mental health",
        "narrowing_steps": [
            {"id": "context", "question_focus": "current emotional landscape", "examples": ["stress", "burnout", "anxiety", "life transition", "motivation"]},
            {"id": "friction", "question_focus": "what makes it hard to maintain wellbeing", "examples": ["no routine", "isolation", "imposter syndrome", "overwhelm"]},
            {"id": "opportunity", "question_focus": "what supportive systems would help"},
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
    {"id": "mental_health", "label": "Mind & mental health", "icon": "brain"},
]

# Map domain id → label for quick lookup
DOMAIN_LABELS = {d["id"]: d["label"] for d in DOMAIN_OPTIONS}


from backend.prompts.discovery import (
    DISCOVERY_SCHEMA_GENERATION_PROMPT as SCHEMA_GENERATION_PROMPT,
    DISCOVERY_OPENING_PROMPT as OPENING_PROMPT,
    DISCOVERY_ELICITATION_PROMPT as ELICITATION_PROMPT,
    DISCOVERY_SIGNAL_EXTRACTION_PROMPT as SIGNAL_EXTRACTION_PROMPT,
    DISCOVERY_PROJECT_PROPOSAL_PROMPT as PROJECT_PROPOSAL_PROMPT,
    DISCOVERY_MODEL_SUMMARY_PROMPT,
    DISCOVERY_UNCERTAINTY_PROMPT,
    DISCOVERY_CROSS_DOMAIN_PROMPT,
    DISCOVERY_ENGAGEMENT_PROMPT,
)


# ── Phase detection (deterministic, no LLM) ────────────────────────

def infer_phase(signals: dict) -> str:
    """Determine conversation phase from accumulated signals."""
    if not signals.get("context"):
        return "orienting"
    if len(signals.get("frictions", [])) < 2 or not signals.get("tools_used"):
        return "friction"
    if not signals.get("opportunities"):
        return "solution_space"
    return "converging"


# ── Engine ──────────────────────────────────────────────────────────

class DiscoveryEngine:
    """Drives domain-based agency discovery conversations."""

    def __init__(self):
        # Accumulated research topics per user:domain, executed in batch before proposals
        self._accumulated_research: dict[str, list[str]] = {}

    def select_domains(self, user_id: str, domains: list[str], db: Session) -> dict:
        """Record selected domains and generate schemas. Does NOT start conversations."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        user.selected_domains = list(domains)

        # Create DiscoveryDomain records and generate schemas
        domain_records = []
        for domain in domains:
            if domain not in DOMAIN_LABELS:
                continue
            dd = db.query(DiscoveryDomain).filter_by(user_id=user_id, domain=domain).first()
            if not dd:
                dd = DiscoveryDomain(
                    user_id=user_id,
                    domain=domain,
                    status="pending",
                )
                db.add(dd)
                db.flush()
            # Generate (or refresh) personalized schema
            dd.schema = self._generate_schema(user, domain)
            domain_records.append(dd)

        db.commit()

        return {
            "domains": [
                {
                    "domain": d.domain,
                    "label": (d.schema or {}).get("label", DOMAIN_LABELS.get(d.domain, d.domain)),
                    "status": d.status,
                }
                for d in domain_records
            ],
        }

    def activate_domain(self, user_id: str, domain_name: str, db: Session) -> dict:
        """Activate a specific domain for chatting. Generates opening if needed."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        domain = db.query(DiscoveryDomain).filter_by(user_id=user_id, domain=domain_name).first()
        if not domain:
            raise ValueError(f"Domain {domain_name} not found for user {user_id}")

        # Deactivate other domains, set this one as active
        other_active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").all()
        for d in other_active:
            if d.domain != domain_name:
                d.status = "explored" if d.conversation else "pending"
        domain.status = "active"
        db.flush()

        # Generate opening if no conversation exists yet
        if not domain.conversation:
            result = self._generate_opening(user, domain, db)
            db.commit()
            return result

        # Return last message from existing conversation
        db.commit()
        last_assistant = None
        for msg in reversed(domain.conversation or []):
            if msg.get("role") == "assistant":
                last_assistant = msg
                break

        return {
            "message": last_assistant["content"] if last_assistant else "",
            "actions": [],
            "domain": domain.domain,
        }

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
                    "label": (d.schema or {}).get("label", DOMAIN_LABELS.get(d.domain, d.domain)),
                    "status": d.status,
                    "depth": d.depth,
                    "conversation": d.conversation or [],
                    "proposed_projects": d.proposed_projects or [],
                }
                for d in domains
            ],
            "active_domain": active.domain if active else None,
        }

    def process_response(self, user_id: str, message: str, db: Session, domain_name: Optional[str] = None) -> dict:
        """Process a user response in a domain conversation."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        if domain_name:
            active = db.query(DiscoveryDomain).filter_by(user_id=user_id, domain=domain_name).first()
        else:
            active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").first()
        if not active:
            return {"message": "No active domain to explore. Select domains first.", "actions": [], "domain": None}

        schema = active.schema or {}
        if not schema:
            return {"message": "Unknown domain.", "actions": [], "domain": active.domain}

        # Save user message to conversation
        conv = list(active.conversation or [])
        conv.append({"role": "user", "content": message})

        # Conditional backend activity based on conversation phase
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        signals = active.signals or {}
        phase = infer_phase(signals)

        parallel_analysis = {}
        new_signals = {}

        # Always extract signals (cheap, essential backbone)
        include = {"signals"}

        # Engagement: only when tone/engagement is unclear
        prev_lengths = [len(m["content"]) for m in conv if m["role"] == "user"]
        msg_len = len(message.split())
        prev_msg_words = len(conv[-3]["content"].split()) if len(conv) >= 3 and conv[-3]["role"] == "user" else msg_len
        if msg_len < 15 or abs(msg_len - prev_msg_words) > 30:
            include.add("engagement")

        # Uncertainty: only in later phases where it adds value
        if phase in ("solution_space", "converging"):
            include.add("uncertainty")

        # Cross-domain: only after friction phase and if other domains have signals
        if phase in ("friction", "solution_space", "converging"):
            include.add("patterns")

        if include == {"signals"}:
            # Lightweight path: just extract signals, no parallel call needed
            try:
                new_signals = self._extract_signals(active, schema, message, conv)
            except Exception as e:
                logger.warning(f"Signal extraction failed: {e}")
        else:
            parallel_analysis = self._analyze_parallel(
                active, schema, message, conv_text, user_id, db,
                include=include,
            )
            new_signals = parallel_analysis.pop("signals", {}) or {}

        try:
            merged = self._merge_signals(active.signals or {}, new_signals)
        except Exception as e:
            logger.warning(f"Signal merge failed: {e}")
            merged = active.signals or {}

        # Accumulate research topics for batch execution before proposals
        research_raw = merged.pop("research", None)
        if research_raw and isinstance(research_raw, str) and research_raw.strip():
            from backend.services.memory import already_researched
            if not already_researched(user_id, research_raw.strip(), db):
                key = f"{user_id}:{active.domain}"
                self._accumulated_research.setdefault(key, []).append(research_raw.strip())
                logger.debug(f"Accumulated research topic: {research_raw.strip()[:60]}")

        active.signals = dict(merged)
        active.depth = (active.depth or 0) + 1
        active.conversation = conv
        db.flush()

        # Decide next action
        action = self._should_advance(active, schema)

        if action == "propose_projects":
            result = self._propose_projects(user, active, schema, conv, db)
        else:
            result = self._generate_next(user, active, schema, conv, db, parallel_analysis=parallel_analysis)

            # Handle agent_task from elicitation — accumulate auto-research, keep manual button
            agent_task = result.pop("agent_task", None)
            if agent_task and isinstance(agent_task, dict) and agent_task.get("description"):
                if agent_task.get("auto"):
                    # Accumulate for batch execution before proposals
                    key = f"{user_id}:{active.domain}"
                    self._accumulated_research.setdefault(key, []).append(agent_task["description"])
                    logger.debug(f"Accumulated agent research: {agent_task['description'][:60]}")
                else:
                    result.setdefault("actions", []).insert(0, {
                        "label": "Research this",
                        "description": agent_task["description"][:80],
                        "action_text": f"agent_run:{agent_task['description']}",
                    })

        # Save assistant message
        conv.append({"role": "assistant", "content": result["message"]})
        active.conversation = list(conv)
        db.commit()

        # Extract insights from this exchange
        from backend.services.memory import extract_insights
        extract_insights(user.id, message, result.get("message", ""), "discovery", active.domain, db)

        result["domain"] = active.domain
        result["depth"] = active.depth

        # When proposing, attach accumulated research topics for batch execution
        if action == "propose_projects":
            key = f"{user_id}:{active.domain}"
            accumulated = self._accumulated_research.pop(key, [])
            if accumulated:
                result["_accumulated_topics"] = accumulated

        return result

    def accept_projects(self, user_id: str, project_indices: list[int], db: Session, finalize: bool = False, domain: str | None = None) -> list[dict]:
        """Create Projects from proposals. Only advances domain when finalize=True or all proposals are accepted."""
        if domain:
            active = db.query(DiscoveryDomain).filter_by(user_id=user_id, domain=domain).first()
        else:
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

        # Only complete domain and advance when accepting all proposals or explicitly finalizing
        all_accepted = len(project_indices) >= len(proposals)
        if finalize or all_accepted:
            active.status = "completed"
            db.flush()
            next_result = self._advance_to_next(user_id, db)
        else:
            next_result = {"next_domain": None, "opening": None, "all_complete": False}

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
        total_depth = 0
        for d in domains:
            if d.signals:
                all_signals[d.domain] = d.signals
            total_depth += d.depth

        # Generate model summary only if user had meaningful conversations
        try:
            if total_depth < 2 or not all_signals:
                user.model_summary = "Complete a few discovery conversations to build your personalized profile."
                logger.info(f"Skipped model summary generation - insufficient data (depth={total_depth})")
            else:
                user.model_summary = self._generate_model_summary(user.name, all_signals)
            user.onboarding_info = json.dumps(all_signals)
        except Exception as e:
            logger.warning(f"Model summary generation failed: {e}")

        db.commit()
        return {"status": "complete", "model_summary": user.model_summary}

    def regenerate_schema(self, user_id: str, domain_name: str, db: Session) -> dict:
        """Re-generate the schema for an existing domain based on updated user info."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        domain = db.query(DiscoveryDomain).filter_by(user_id=user_id, domain=domain_name).first()
        if not domain:
            raise ValueError(f"Domain {domain_name} not found for user {user_id}")

        domain.schema = self._generate_schema(user, domain_name)
        db.commit()
        return domain.schema

    async def run_agent_task(self, user_id: str, task_description: str, db: Session) -> dict:
        """Run a user-initiated agent task during discovery and return next message."""
        user = db.query(UserProfile).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="active").first()
        if not active:
            return {"message": "No active domain.", "actions": [], "domain": None}

        schema = active.schema or {}
        conv = list(active.conversation or [])

        # Run the agent
        agent_result = await self._run_discovery_agent(task_description, user, active)

        # Append agent result to conversation as system context
        conv.append({"role": "system", "content": f"[Agent research result]: {agent_result}"})
        active.conversation = list(conv)
        db.flush()

        # Generate next message with agent result in context
        result = self._generate_next(user, active, schema, conv, db)

        conv.append({"role": "assistant", "content": result["message"]})
        active.conversation = list(conv)
        db.commit()

        result["domain"] = active.domain
        result["depth"] = active.depth
        return result

    async def _run_discovery_agent(self, task: str, user: UserProfile, domain: DiscoveryDomain, timeout: float = 90.0) -> str:
        """Run a lightweight agent during discovery and return the result text."""
        import asyncio

        instruction = (
            f"You are doing a research task to help {user.name} during a discovery conversation "
            f"about {(domain.schema or {}).get('label', domain.domain)}.\n\n"
            f"Task: {task}\n\n"
            f"For each tool, service, or solution you find, provide:\n"
            f"- Name with a hyperlink to its website (markdown format: [Name](url))\n"
            f"- 1-sentence description of what it does and why it's relevant\n"
            f"- Pricing (free tier? cost?)\n"
            f"- Key differentiator vs alternatives\n\n"
            f"Return 2-4 findings as bullet points. Be specific and practical, not generic."
        )

        from backend.services.claude_code_executor import executor

        # Build the command the same way executor does, but manage the process directly with a timeout
        cmd = [
            "claude", "-p", instruction,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--system-prompt", executor.SYSTEM_PROMPT,
            "--allowedTools", "WebSearch,WebFetch,Read,Bash",
            "--max-turns", "5",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result_text = ""
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            for line in stdout.decode("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "result":
                        result_text = data.get("result", "")
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            logger.warning(f"Discovery agent timed out after {timeout}s, killing process: {task[:60]}")
            process.kill()
            await process.wait()
        except Exception as e:
            logger.warning(f"Discovery agent failed: {e}")
            process.kill()
            await process.wait()

        return result_text or "No results found."

    async def research_and_refine_proposals(self, user_id: str, result: dict, db: Session,
                                             accumulated_topics: list[str] | None = None) -> dict:
        """Research existing tools/solutions and refine project proposals accordingly.

        If accumulated_topics are provided (research noted during Q&A), they are
        included in the research task so all research happens in a single batch.
        """
        proposals = result.get("proposed_projects", [])
        if not proposals:
            return result

        user = db.query(UserProfile).filter_by(id=user_id).first()
        active = db.query(DiscoveryDomain).filter_by(user_id=user_id, status="explored").first()
        if not user or not active:
            return result

        # Build a research task based on the proposals and user context
        signals = active.signals or {}
        tools_used = signals.get("tools_used", [])
        frictions = signals.get("frictions", [])

        proposal_summaries = "\n".join(
            f"- {p.get('name', 'Project')}: {p.get('description', '')}" for p in proposals
        )

        # Include accumulated research topics from conversation
        accumulated_section = ""
        if accumulated_topics:
            # Deduplicate
            seen = set()
            unique = []
            for t in accumulated_topics:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    unique.append(t)
            topics_text = "\n".join(f"- {t}" for t in unique[:5])
            accumulated_section = (
                f"\n\nAlso research these topics noted during our conversation:\n"
                f"{topics_text}\n"
            )
            logger.info(f"Including {len(unique)} accumulated research topics in proposal research")

        research_task = (
            f"Research the best EXISTING tools, services, and integrations for these needs:\n"
            f"{proposal_summaries}\n\n"
            f"User's current tools: {', '.join(tools_used) if tools_used else 'not specified'}\n"
            f"Pain points: {', '.join(frictions) if frictions else 'not specified'}\n"
            f"{accumulated_section}\n"
            f"Find real products/services that solve these problems. "
            f"For each, note: name, what it does, pricing (if available), and how it integrates "
            f"with the user's existing tools. Prefer solutions that integrate with what they already use."
        )

        research_result = await self._run_discovery_agent(research_task, user, active)

        # Store research insights for memory
        try:
            from backend.services.memory import extract_research_insights
            extract_research_insights(user.id, research_task, research_result, active.domain, db)
        except Exception as e:
            logger.warning(f"Failed to extract research insights: {e}")

        # Now regenerate proposals with the research context
        schema = active.schema or {}
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in (active.conversation or [])[-10:])
        dp = get_domain_prompts(active.domain)

        from backend.prompts.discovery import DISCOVERY_PROJECT_PROPOSAL_PROMPT as PROJECT_PROPOSAL_PROMPT
        prompt = PROJECT_PROPOSAL_PROMPT.format(
            domain_label=schema.get("label", active.domain),
            user_name=user.name,
            signals_text=json.dumps(signals, indent=2),
            conversation_text=conv_text,
            domain_project_guidance=dp.get("project_guidance", "Propose specific, actionable projects."),
        )
        prompt += f"\n\n## Research on existing solutions\n{research_result}\n\nUse this research to recommend REAL tools and services, not hypothetical ones."

        try:
            # Use gpt-4o for reliable JSON output
            raw = chat(prompt, model=MODEL_JSON)
            cleaned = re.sub(r"<brainstorm>.*?</brainstorm>", "", raw, flags=re.DOTALL).strip()
            proposals = parse_json(cleaned)
            if not isinstance(proposals, list):
                proposals = [proposals]
        except Exception as e:
            logger.warning(f"Refined proposal generation failed: {e}")
            return result  # Fall back to original proposals

        # Update stored proposals
        active.proposed_projects = list(proposals)
        db.flush()

        # Brief conversational note — full proposals render in the side panel
        names = [p.get("name", "project") for p in proposals]
        if len(names) == 1:
            brief = f"I researched existing solutions and refined a project idea — **{names[0]}**. Take a look on the right!"
        else:
            brief = f"I researched existing solutions and refined {len(names)} project ideas. Check them out on the right!"

        # Update conversation with brief message
        conv = list(active.conversation or [])
        if conv and conv[-1].get("role") == "assistant":
            conv[-1] = {"role": "assistant", "content": brief}
        else:
            conv.append({"role": "assistant", "content": brief})
        active.conversation = list(conv)
        db.commit()

        return {
            "message": brief,
            "actions": [],
            "proposed_projects": proposals,
            "domain": active.domain,
            "depth": active.depth,
        }

    # ── Internal helpers ────────────────────────────────────────────

    def _analyze_parallel(self, domain: DiscoveryDomain, schema: dict, message: str, conv_text: str, user_id: str, db: Session, include: set = None) -> dict:
        """Run parallel analysis calls, filtered by `include` set."""
        include = include or {"signals", "uncertainty", "engagement", "patterns"}
        label = schema.get("label", domain.domain)
        existing_signals = json.dumps(domain.signals or {})
        dp = get_domain_prompts(domain.domain)

        prompts = {}

        if "signals" in include:
            prompts["signals"] = SIGNAL_EXTRACTION_PROMPT.format(
                domain_label=label,
                conversation_text=conv_text,
                latest_message=message,
                existing_signals=existing_signals,
                domain_signal_hints=dp.get("signal_hints", ""),
            )

        if "uncertainty" in include:
            prompts["uncertainty"] = DISCOVERY_UNCERTAINTY_PROMPT.format(
                domain_label=label,
                conversation_text=conv_text,
                latest_message=message,
                existing_signals=existing_signals,
            )

        if "engagement" in include:
            prompts["engagement"] = DISCOVERY_ENGAGEMENT_PROMPT.format(
                conversation_text=conv_text,
                latest_message=message,
            )

        if "patterns" in include:
            other_domains = db.query(DiscoveryDomain).filter(
                DiscoveryDomain.user_id == user_id,
                DiscoveryDomain.domain != domain.domain,
            ).all()
            other_signals = {d.domain: d.signals for d in other_domains if d.signals}
            if other_signals:
                prompts["patterns"] = DISCOVERY_CROSS_DOMAIN_PROMPT.format(
                    domain_label=label,
                    latest_message=message,
                    other_domain_signals=json.dumps(other_signals, indent=2),
                )

        try:
            results = chat_json_parallel(prompts, model=MODEL_MINI)
        except Exception as e:
            logger.warning(f"Parallel analysis failed: {e}")
            return {}

        return results

    def _generate_schema(self, user: UserProfile, domain_name: str) -> dict:
        """LLM call to generate a personalized narrowing schema for a domain."""
        label = DOMAIN_LABELS.get(domain_name, domain_name)
        example = DOMAIN_SCHEMA_EXAMPLES.get(domain_name, list(DOMAIN_SCHEMA_EXAMPLES.values())[0])

        # Build user context from whatever we know
        context_parts = []
        if user.name:
            context_parts.append(f"Name: {user.name}")
        if user.model_summary:
            context_parts.append(f"Profile: {user.model_summary}")
        if user.onboarding_info:
            context_parts.append(f"Background: {user.onboarding_info}")
        user_context = "\n".join(context_parts) if context_parts else "New user — no prior information available."

        prompt = SCHEMA_GENERATION_PROMPT.format(
            user_name=user.name or "the user",
            domain_label=label,
            user_context=user_context,
            example_schema=json.dumps(example, indent=2),
        )

        try:
            schema = chat_json(prompt, model=MODEL_MINI)
            # Validate structure
            if not isinstance(schema.get("narrowing_steps"), list) or not schema.get("agent_capabilities"):
                raise ValueError("Invalid schema structure")
            # Append metric step
            schema["narrowing_steps"].append(METRIC_STEP)
            schema.setdefault("label", label)
            return schema
        except Exception as e:
            logger.warning(f"Schema generation failed for {domain_name}: {e}, using fallback")
            fallback = DOMAIN_SCHEMA_EXAMPLES.get(domain_name, {"label": label, "narrowing_steps": [], "agent_capabilities": []})
            result = {
                "label": fallback.get("label", label),
                "narrowing_steps": list(fallback.get("narrowing_steps", [])) + [METRIC_STEP],
                "agent_capabilities": list(fallback.get("agent_capabilities", [])),
            }
            return result

    def _generate_opening(self, user: UserProfile, domain: DiscoveryDomain, db: Session) -> dict:
        """Generate the opening message for a domain conversation."""
        schema = domain.schema or {}
        dp = get_domain_prompts(domain.domain)

        # Pull recent home chat messages so the domain opener can reference prior context
        home_context = ""
        home_project = db.query(Project).filter_by(user_id=user.id, domain="home").first()
        if home_project:
            recent_home = (
                db.query(ChatMessage)
                .filter_by(project_id=home_project.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
                .all()
            )
            if recent_home:
                recent_home.reverse()
                lines = [f"{m.role}: {m.content}" for m in recent_home]
                home_context = (
                    "\n\n## Recent Home Chat Context\n"
                    "The user was just chatting in their Home space before navigating here. "
                    "Use this context to skip questions they've already answered and pick up where they left off.\n\n"
                    + "\n".join(lines)
                )

        prompt = OPENING_PROMPT.format(
            user_name=user.name,
            domain_label=schema.get("label", domain.domain),
            capabilities=", ".join(schema.get("agent_capabilities", [])),
            domain_persona=dp.get("persona", "Be helpful and conversational."),
        )
        prompt += home_context
        try:
            result = chat_json(prompt, retries=2)
        except Exception as e:
            logger.warning(f"Opening generation failed: {e}")
            result = {
                "message": f"Let's explore how I can help with your {schema.get('label', domain.domain).lower()}. Tell me a bit about your situation — what's going on in this area of your life?",
                "actions": [],
            }

        # Save to conversation
        domain.conversation = [{"role": "assistant", "content": result.get("message", "")}]
        db.flush()

        result.setdefault("actions", [])
        result["domain"] = domain.domain
        return result

    def _extract_signals(self, domain: DiscoveryDomain, schema: dict, message: str, conv: list) -> dict:
        """LLM call to extract structured signals from the conversation."""
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        dp = get_domain_prompts(domain.domain)
        prompt = SIGNAL_EXTRACTION_PROMPT.format(
            domain_label=schema.get("label", domain.domain),
            conversation_text=conv_text,
            latest_message=message,
            existing_signals=json.dumps(domain.signals or {}),
            domain_signal_hints=dp.get("signal_hints", ""),
        )
        return chat_json(prompt, model=MODEL_MINI)

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
        steps = schema.get("narrowing_steps", [])
        depth = domain.depth or 0
        signals = domain.signals or {}
        phase = infer_phase(signals)

        # If we've exhausted the schema steps, propose
        if depth >= len(steps):
            return "propose_projects"

        # If converging (has context + frictions + tools + opportunities) and
        # we have any metric signal, propose — don't keep asking
        has_metric = bool(signals.get("selected_metric") or signals.get("metric_candidates"))
        if phase == "converging" and has_metric and depth >= 2:
            return "propose_projects"

        # Even without a metric, if converging and depth >= 3, propose
        if phase == "converging" and depth >= 3:
            return "propose_projects"

        if depth >= 6:
            return "propose_projects"

        return "ask_more"

    def _generate_next(self, user: UserProfile, domain: DiscoveryDomain, schema: dict, conv: list, db: Session = None, parallel_analysis: Optional[dict] = None) -> dict:
        """Generate the next conversational message."""
        steps = schema.get("narrowing_steps", [])
        current_step_idx = min(domain.depth or 0, len(steps) - 1)
        step = steps[current_step_idx] if steps else {"question_focus": "their situation", "examples": []}

        signals_text = json.dumps(domain.signals or {}, indent=2) if domain.signals else "Nothing yet"
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        step_examples = f"Examples: {', '.join(step.get('examples', []))}" if step.get("examples") else ""

        attached_context = ""
        if db:
            attached_context = get_context_text(db, user.id, discovery_domain_id=domain.id)

        # Format parallel analysis for injection into prompt
        analysis_text = "None available"
        if parallel_analysis:
            parts = []
            if parallel_analysis.get("uncertainty"):
                u = parallel_analysis["uncertainty"]
                parts.append(f"**Uncertainties**: {', '.join(u.get('uncertainties', []))}")
                if u.get("researchable"):
                    parts.append(f"**Researchable**: {', '.join(u['researchable'])}")
                if u.get("assumptions"):
                    parts.append(f"**Unvalidated assumptions**: {', '.join(u['assumptions'])}")
            if parallel_analysis.get("patterns"):
                p = parallel_analysis["patterns"]
                if p.get("connections"):
                    parts.append(f"**Cross-domain connections**: {', '.join(p['connections'])}")
                if p.get("themes"):
                    parts.append(f"**Recurring themes**: {', '.join(p['themes'])}")
                if p.get("contradictions"):
                    parts.append(f"**Tensions to explore**: {', '.join(p['contradictions'])}")
            if parallel_analysis.get("engagement"):
                e = parallel_analysis["engagement"]
                parts.append(f"**Engagement**: {e.get('engagement', '?')} | Specificity: {e.get('specificity', '?')} | Readiness: {e.get('readiness', '?')}")
                if e.get("approach_hint"):
                    parts.append(f"**Approach hint**: {e['approach_hint']}")
            if parts:
                analysis_text = "\n".join(parts)

        dp = get_domain_prompts(domain.domain)
        prompt = ELICITATION_PROMPT.format(
            user_name=user.name,
            domain_label=schema.get("label", domain.domain),
            capabilities=", ".join(schema.get("agent_capabilities", [])),
            step_focus=step["question_focus"],
            step_examples=step_examples,
            signals_text=signals_text,
            conversation_text=conv_text,
            attached_context=attached_context or "None",
            parallel_analysis=analysis_text,
            domain_persona=dp.get("persona", "Be helpful and conversational."),
            domain_guidance=dp.get("elicitation_guidance", "Ask thoughtful, specific questions."),
        )

        try:
            result = chat_json(prompt, retries=2)
        except Exception as e:
            logger.warning(f"Elicitation generation failed: {e}")
            result = {"message": f"Tell me more about {step['question_focus']}.", "actions": []}

        result.setdefault("actions", [])
        return result

    def _propose_projects(self, user: UserProfile, domain: DiscoveryDomain, schema: dict, conv: list, db: Session) -> dict:
        """Generate project proposals from accumulated signals."""
        signals_text = json.dumps(domain.signals or {}, indent=2)
        conv_text = "\n".join(f"{m['role']}: {m['content']}" for m in conv[-10:])
        dp = get_domain_prompts(domain.domain)

        prompt = PROJECT_PROPOSAL_PROMPT.format(
            domain_label=schema.get("label", domain.domain),
            user_name=user.name,
            signals_text=signals_text,
            conversation_text=conv_text,
            domain_project_guidance=dp.get("project_guidance", "Propose specific, actionable projects."),
        )

        try:
            # Use gpt-4o for reliable JSON output (gpt-5 returns empty responses)
            raw = chat(prompt, model=MODEL_JSON)
            cleaned = re.sub(r"<brainstorm>.*?</brainstorm>", "", raw, flags=re.DOTALL).strip()
            proposals = parse_json(cleaned)
            if not isinstance(proposals, list):
                proposals = [proposals]
        except Exception as e:
            logger.warning(f"Project proposal generation failed: {e}")
            # Retry with a simpler prompt
            try:
                simple_prompt = (
                    f"Based on this conversation about {schema.get('label', domain.domain)}, "
                    f"propose 1 specific project as a JSON array.\n\n"
                    f"Conversation:\n{conv_text[-1500:]}\n\n"
                    f"The project name must be SPECIFIC to what the user said (not generic).\n"
                    f"Format: [{{\"name\": \"specific name\", \"description\": \"what it does\", "
                    f"\"first_goal\": \"first step\", \"success_metric\": \"metric\", \"metric_target\": \"target\"}}]\n"
                    f"Return ONLY the JSON array."
                )
                proposals = chat_json(simple_prompt, retries=2)
                if not isinstance(proposals, list):
                    proposals = [proposals]
            except Exception as e2:
                logger.warning(f"Project proposal retry also failed: {e2}")
                proposals = [{
                    "name": f"{schema.get('label', domain.domain)} exploration",
                    "description": f"Continue exploring {schema.get('label', domain.domain).lower()} based on what we discussed.",
                    "first_goal": "Review the conversation and identify the most impactful next step.",
                    "success_metric": (domain.signals or {}).get("selected_metric", "progress"),
                    "metric_target": (domain.signals or {}).get("metric_target", "weekly"),
                }]

        domain.proposed_projects = list(proposals)
        domain.status = "explored"
        db.flush()

        # Brief conversational note — full proposals render in the side panel
        names = [p.get("name", "project") for p in proposals]
        if len(names) == 1:
            brief = f"I've put together a project idea based on what we discussed — **{names[0]}**. Take a look on the right and let me know what you think!"
        else:
            brief = f"I've added {len(names)} project ideas on the right based on our conversation. Take a look and accept the ones that resonate!"
        return {"message": brief, "actions": [], "proposed_projects": proposals}

    def _advance_to_next(self, user_id: str, db: Session) -> dict:
        """Activate the next pending domain or signal completion."""
        next_domain = db.query(DiscoveryDomain).filter_by(
            user_id=user_id, status="pending"
        ).order_by(DiscoveryDomain.created_at).first()

        if next_domain:
            next_domain.status = "active"
            db.flush()
            user = db.query(UserProfile).filter_by(id=user_id).first()
            opening = self._generate_opening(user, next_domain, db)
            return {"next_domain": next_domain.domain, "opening": opening, "all_complete": False}
        else:
            return {"next_domain": None, "opening": None, "all_complete": True}

    def _generate_model_summary(self, name: str, all_signals: dict) -> str:
        """Generate a user model summary from all domain signals."""
        prompt = DISCOVERY_MODEL_SUMMARY_PROMPT.format(
            name=name,
            signals_json=json.dumps(all_signals, indent=2),
        )
        return chat(prompt)


discovery_engine = DiscoveryEngine()
