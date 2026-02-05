"""Phase-based interaction engine.

Replaces the mediator pipeline for structured project conversations.
Phases: frame → diagnose → decompose → propose → collect → commit → execute

The structure is fixed (phases, block types, transitions).
The content is LLM-generated.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import AgentRun, ChatMessage, Project, UserProfile
from backend.services.llm import chat_messages, parse_json, MODEL_JSON
from backend.services.prompt_builder import build_system_prompt
from backend.services.context_service import get_context_text
from backend.services.memory import extract_insights, retrieve_insights

from backend.prompts.flow.frame import FRAME_PROMPT
from backend.prompts.flow.diagnose import DIAGNOSE_PROMPT
from backend.prompts.flow.decompose import DECOMPOSE_PROMPT
from backend.prompts.flow.research import RESEARCH_TASK_PROMPT
from backend.prompts.flow.propose import PROPOSE_PROMPT
from backend.prompts.flow.collect import COLLECT_PROMPT
from backend.prompts.flow.commit import COMMIT_PROMPT

logger = logging.getLogger(__name__)


# Phase transition order (deterministic)
PHASE_ORDER = ["frame", "diagnose", "decompose", "propose", "collect", "commit", "execute"]


class FlowEngine:
    """Core engine for phase-based structured interactions."""

    def process_message(
        self,
        project_id: int,
        user_message: Optional[str],
        db: Session,
    ) -> dict:
        """Main entry point. Returns {message, actions, blocks, phase}.

        This is called by the chat endpoint in projects.py.
        """
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        user = db.query(UserProfile).filter_by(id=project.user_id).first()
        if not user:
            raise ValueError(f"User not found for project {project_id}")

        state = dict(project.flow_state or {})

        # No user message and no phase yet — greeting or auto-start from nav context
        if not user_message and not state.get("phase"):
            # Only auto-start with description if project was created via navigation from home chat
            # (suggested_by_system=True). Fresh "New project" clicks should get a greeting instead.
            if project.suggested_by_system and project.description and project.description.strip():
                nav_context = project.description.strip()
                db.add(ChatMessage(project_id=project.id, role="user", content=nav_context))
                db.commit()
                return self._run_frame(project, user, nav_context, state, db)
            return self._handle_greeting(project, user, db)

        # No user message but already have conversation — return last message
        if not user_message:
            return self._return_last_message(project, db)

        # Save user message
        db.add(ChatMessage(project_id=project_id, role="user", content=user_message))
        db.commit()

        # First message: run Frame phase
        if not state.get("phase"):
            return self._run_frame(project, user, user_message, state, db)

        # Subsequent messages: resolve phase and generate
        current_phase = state["phase"]

        if current_phase == "frame":
            # Frame already ran, user is responding — move to diagnose
            return self._run_diagnose(project, user, user_message, state, db)

        if current_phase == "diagnose":
            return self._run_diagnose(project, user, user_message, state, db)

        if current_phase == "decompose":
            # User responded to decomposition — run propose (with research)
            return self._run_propose(project, user, user_message, state, db)

        if current_phase == "propose":
            # User responded to proposals — move to collect or commit
            return self._advance_from_propose(project, user, user_message, state, db)

        if current_phase == "collect":
            return self._advance_from_collect(project, user, user_message, state, db)

        if current_phase == "commit":
            return self._handle_commit_response(project, user, user_message, state, db)

        # Unknown phase — this is a bug, not a recoverable state
        raise ValueError(f"Unknown flow phase: {current_phase!r} for project {project.id}")

    # ── Phase runners ─────────────────────────────────────────────────

    def _run_frame(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Frame phase: understand the goal, plan the interaction."""
        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)

        user_context = self._build_user_context(user)

        prompt_text = FRAME_PROMPT.format(
            user_context=user_context,
            user_message=user_message,
            conversation_history=self._format_history(history),
        )

        raw = chat_messages(
            base_prompt,
            [{"role": "user", "content": prompt_text}],
            json_mode=True,
        )
        result = parse_json(raw)

        # Auto-assign domain from LLM classification
        domain = result.get("domain")
        valid_domains = {"work", "learning", "health", "creative", "money", "mind"}
        if domain in valid_domains and not project.domain:
            project.domain = domain

        # Determine next phase based on interaction_plan
        plan = result.get("interaction_plan", {})
        skip = plan.get("skip_phases", [])
        diagnostic_questions = plan.get("diagnostic_questions", [])

        if "diagnose" in skip or not diagnostic_questions:
            next_phase = "decompose" if "decompose" not in skip else "propose"
        else:
            next_phase = "diagnose"

        # Update flow state
        state["phase"] = next_phase
        state["interaction_plan"] = plan
        state["diagnostic_answers"] = {}
        state["questions_asked"] = 0
        project.flow_state = state
        db.flush()

        # Build response
        blocks = result.get("blocks", [])
        message = result.get("message", "")

        # If we're moving directly to diagnose, ask the first question now
        if next_phase == "diagnose" and diagnostic_questions:
            first_q = diagnostic_questions[0]
            blocks = self._question_to_block(first_q, 0)
            state["questions_asked"] = 1
            project.flow_state = state
            db.flush()

        response = {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "frame",
        }

        # Save assistant message
        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="frame",
        ))
        db.commit()

        # Extract insights
        extract_insights(user.id, user_message, message, "project", str(project.id), db)

        return response

    def _run_diagnose(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Diagnose phase: ask structured questions, one at a time."""
        plan = state.get("interaction_plan", {})
        all_questions = plan.get("diagnostic_questions", [])
        answers = state.get("diagnostic_answers", {})
        questions_asked = state.get("questions_asked", 0)

        # Build remaining questions list
        remaining = all_questions[questions_asked:]

        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)
        user_context = self._build_user_context(user)

        prompt_text = DIAGNOSE_PROMPT.format(
            user_context=user_context,
            interaction_plan=json.dumps(plan, indent=2),
            remaining_questions=[q.get("question", q) if isinstance(q, dict) else q for q in remaining],
            answers_so_far=json.dumps(answers, indent=2),
            conversation_history=self._format_history(history),
            user_message=user_message,
        )

        raw = chat_messages(
            base_prompt,
            history + [{"role": "user", "content": prompt_text}],
            json_mode=True,
        )
        result = parse_json(raw)

        # Update answers
        new_answers = result.get("diagnostic_answers", {})
        answers.update(new_answers)
        state["diagnostic_answers"] = answers
        state["questions_asked"] = questions_asked + 1

        # Check if diagnose is complete
        phase_complete = result.get("phase_complete", False)
        no_more_questions = questions_asked + 1 >= len(all_questions)

        if phase_complete or no_more_questions:
            skip = plan.get("skip_phases", [])
            if "decompose" not in skip:
                # Auto-run decompose (no user input needed)
                state["phase"] = "decompose"
                project.flow_state = state
                db.flush()

                # Save the diagnose response first
                blocks = result.get("blocks", [])
                message = result.get("message", "")
                if message:
                    db.add(ChatMessage(
                        project_id=project.id,
                        role="assistant",
                        content=message,
                        actions=[],
                        blocks=blocks,
                        phase="diagnose",
                    ))
                    db.commit()

                extract_insights(user.id, user_message, message, "project", str(project.id), db)

                # Auto-run decompose
                return self._run_decompose(project, user, state, db)
            else:
                state["phase"] = "propose"
                project.flow_state = state
                db.flush()

                # Save diagnose response, then auto-run propose
                blocks = result.get("blocks", [])
                message = result.get("message", "")
                if message:
                    db.add(ChatMessage(
                        project_id=project.id,
                        role="assistant",
                        content=message,
                        actions=[],
                        blocks=blocks,
                        phase="diagnose",
                    ))
                    db.commit()

                extract_insights(user.id, user_message, message, "project", str(project.id), db)

                return self._run_propose(project, user, user_message, state, db)
        else:
            state["phase"] = "diagnose"

        project.flow_state = state
        db.flush()

        blocks = result.get("blocks", [])
        message = result.get("message", "")

        response = {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "diagnose",
        }

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="diagnose",
        ))
        db.commit()

        extract_insights(user.id, user_message, message, "project", str(project.id), db)

        return response

    def _run_decompose(
        self,
        project: Project,
        user: UserProfile,
        state: dict,
        db: Session,
    ) -> dict:
        """Decompose phase: break goal into sub-problems."""
        plan = state.get("interaction_plan", {})
        answers = state.get("diagnostic_answers", {})
        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)
        user_context = self._build_user_context(user)

        # Reconstruct the user's goal from the first message
        user_goal = self._get_user_goal(project.id, db)

        prompt_text = DECOMPOSE_PROMPT.format(
            user_context=user_context,
            user_goal=user_goal,
            diagnostic_answers=json.dumps(answers, indent=2),
            conversation_history=self._format_history(history),
        )

        raw = chat_messages(
            base_prompt,
            [{"role": "user", "content": prompt_text}],
            json_mode=True,
        )
        result = parse_json(raw)

        # Save decomposition in state
        state["decomposition"] = result.get("synthesis", "")
        state["decomposition_blocks"] = result.get("blocks", [])
        state["phase"] = "propose"
        project.flow_state = state
        db.flush()

        blocks = result.get("blocks", [])
        message = result.get("message", "")

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="decompose",
        ))
        db.commit()

        return {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "decompose",
            "auto_continue": True,
        }

    def _run_propose(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Propose phase: generate research-backed proposal cards.

        This runs the 3-call research pipeline:
        1. LLM generates research instruction
        2. Agent executes web search (placeholder — runs inline for now)
        3. LLM generates proposals with research context
        """
        plan = state.get("interaction_plan", {})
        answers = state.get("diagnostic_answers", {})
        decomposition = state.get("decomposition", "")
        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)
        user_context = self._build_user_context(user)
        user_goal = self._get_user_goal(project.id, db)

        # Call 1: Generate research instruction
        research_results = state.get("research_results", "")
        if not research_results:
            research_prompt = RESEARCH_TASK_PROMPT.format(
                user_goal=user_goal,
                decomposition=decomposition or json.dumps(plan.get("likely_proposals", []), indent=2),
                diagnostic_answers=json.dumps(answers, indent=2),
                user_context=user_context,
            )
            raw = chat_messages(
                "You generate research tasks. Respond with valid JSON only.",
                [{"role": "user", "content": research_prompt}],
                json_mode=True,
            )
            research_task = parse_json(raw)
            research_instruction = research_task.get("research_instruction", "")
            research_title = research_task.get("research_title", "Research")

            # Call 2: Execute research (inline for now — Phase C will add streaming)
            if research_instruction:
                from backend.services.llm import chat, MODEL_JSON as _MODEL
                research_results = chat(
                    f"You are a research agent. Execute this research task and return your findings:\n\n{research_instruction}\n\nBe specific. Include real tool names, pricing, and URLs where possible.",
                    model=_MODEL,
                )

                # Save research results
                state["research_results"] = research_results
                project.flow_state = state
                db.flush()

                # Save as artifact for workspace panel
                from backend.database import Artifact
                db.add(Artifact(
                    project_id=project.id,
                    artifact_type="research",
                    title=f"Landscape: {research_title}",
                    content={"markdown": research_results},
                    sources=[],
                ))
                db.commit()

        # Call 3: Generate proposals with research context
        propose_prompt = PROPOSE_PROMPT.format(
            user_context=user_context,
            user_goal=user_goal,
            decomposition=decomposition,
            diagnostic_answers=json.dumps(answers, indent=2),
            research_results=research_results[:4000],
            conversation_history=self._format_history(history),
        )

        raw = chat_messages(
            base_prompt,
            [{"role": "user", "content": propose_prompt}],
            json_mode=True,
        )
        result = parse_json(raw)

        state["phase"] = "collect"
        project.flow_state = state
        db.flush()

        blocks = result.get("blocks", [])
        message = result.get("message", "")

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="propose",
        ))
        db.commit()

        return {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "propose",
        }

    def _advance_from_propose(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Run collect phase: ask targeted context questions for selected proposals."""
        # Parse what the user selected from their message
        state["selected_proposals"] = user_message
        state["phase"] = "collect"
        project.flow_state = state
        db.flush()

        return self._run_collect(project, user, user_message, state, db)

    def _run_collect(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Collect phase: ask targeted questions to personalize proposals."""
        answers = state.get("diagnostic_answers", {})
        selected = state.get("selected_proposals", "")
        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)
        user_context = self._build_user_context(user)

        prompt_text = COLLECT_PROMPT.format(
            user_context=user_context,
            selected_proposals=selected,
            skipped_proposals=state.get("skipped_proposals", ""),
            diagnostic_answers=json.dumps(answers, indent=2),
            conversation_history=self._format_history(history),
        )

        raw = chat_messages(
            base_prompt,
            history + [{"role": "user", "content": prompt_text}],
            json_mode=True,
        )
        result = parse_json(raw)

        # Update context answers
        context = state.get("context_answers", {})
        context.update(result.get("context_answers", {}))
        state["context_answers"] = context

        # Check if collect is complete
        if result.get("phase_complete", False):
            state["phase"] = "commit"
            project.flow_state = state
            db.flush()
            extract_insights(user.id, user_message, result.get("message", ""), "project", str(project.id), db)
            # Auto-run commit
            return self._run_commit(project, user, state, db)

        state["phase"] = "collect"
        project.flow_state = state
        db.flush()

        blocks = result.get("blocks", [])
        message = result.get("message", "")

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="collect",
        ))
        db.commit()

        extract_insights(user.id, user_message, message, "project", str(project.id), db)

        return {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "collect",
        }

    def _advance_from_collect(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Handle collect phase response and advance to commit."""
        # Update context answers from user's response
        context = state.get("context_answers", {})
        context["latest_response"] = user_message
        state["context_answers"] = context
        state["phase"] = "commit"
        project.flow_state = state
        db.flush()

        extract_insights(user.id, user_message, "", "project", str(project.id), db)

        return self._run_commit(project, user, state, db)

    def _run_commit(
        self,
        project: Project,
        user: UserProfile,
        state: dict,
        db: Session,
    ) -> dict:
        """Commit phase: present preferences + summary checklist + build CTA."""
        answers = state.get("diagnostic_answers", {})
        selected = state.get("selected_proposals", "")
        context = state.get("context_answers", {})
        base_prompt = self._build_base_prompt(user, project, db)
        history = self._get_conversation_history(project.id, db)
        user_context = self._build_user_context(user)

        prompt_text = COMMIT_PROMPT.format(
            user_context=user_context,
            selected_proposals=selected,
            context_answers=json.dumps(context, indent=2),
            diagnostic_answers=json.dumps(answers, indent=2),
            conversation_history=self._format_history(history),
        )

        raw = chat_messages(
            base_prompt,
            [{"role": "user", "content": prompt_text}],
            json_mode=True,
        )
        result = parse_json(raw)

        # Save task description for escalation
        state["task_description"] = result.get("task_description", "")
        state["phase"] = "commit"

        # Store metric and notification options for user selection
        state["metric_options"] = result.get("metric_options", [])
        state["notification_options"] = result.get("notification_options", [])

        project.flow_state = state
        db.flush()

        blocks = result.get("blocks", [])
        message = result.get("message", "")

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=blocks,
            phase="commit",
        ))
        db.commit()

        return {
            "message": message,
            "actions": [],
            "blocks": blocks,
            "phase": "commit",
        }

    def _handle_commit_response(
        self,
        project: Project,
        user: UserProfile,
        user_message: str,
        state: dict,
        db: Session,
    ) -> dict:
        """Handle commit phase response: build or adjust."""
        # Parse selections from message format: "build|metric_choice:value|notification_choice:value"
        parts = user_message.split("|")
        action = parts[0].lower().strip()
        selections = {}
        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                selections[key.strip()] = value.strip()

        # Check if user wants to adjust
        if "adjust" in action or "change" in action or "modify" in action:
            # Go back to propose phase
            state["phase"] = "propose"
            project.flow_state = state
            db.flush()

            message = "No problem — what would you like to change?"
            db.add(ChatMessage(
                project_id=project.id,
                role="assistant",
                content=message,
                actions=[],
                blocks=[],
                phase="commit",
            ))
            db.commit()

            return {
                "message": message,
                "actions": [],
                "blocks": [],
                "phase": "commit",
            }

        # User approved — save their preferences and escalate to execution

        # Save selected metric
        metric_choice = selections.get("metric_choice", "")
        metric_options = state.get("metric_options", [])
        selected_metric = next(
            (m for m in metric_options if m.get("value") == metric_choice),
            metric_options[0] if metric_options else None
        )
        if selected_metric:
            project.success_metric = selected_metric.get("name", "")
            project.metric_target = str(selected_metric.get("target", ""))
            project.metric_config = {
                "unit": selected_metric.get("unit", ""),
                "cadence": selected_metric.get("cadence", "weekly"),
                "source": selected_metric.get("source", "self_reported"),
                "prompt": selected_metric.get("prompt"),
                "description": selected_metric.get("description", ""),
            }

        # Save selected notification preferences
        notify_choice = selections.get("notification_choice", "")
        notify_options = state.get("notification_options", [])
        selected_notify = next(
            (n for n in notify_options if n.get("value") == notify_choice),
            notify_options[0] if notify_options else None
        )
        if selected_notify:
            project.notification_prefs = {
                "frequency": selected_notify.get("frequency", "weekly"),
                "update_types": selected_notify.get("update_types", []),
                "description": selected_notify.get("description", ""),
            }

        task_desc = state.get("task_description", "")
        if not task_desc:
            task_desc = f"Work on: {project.description or project.name}"

        message = "Starting work on this now. You'll see progress below as the agent works."

        state["phase"] = "execute"
        project.flow_state = state
        db.flush()

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=message,
            actions=[],
            blocks=[],
            phase="execute",
        ))
        db.commit()

        return {
            "message": message,
            "actions": [],
            "blocks": [],
            "phase": "execute",
            "escalate": True,
            "task_description": task_desc,
        }

    # ── Helpers ───────────────────────────────────────────────────────

    def _handle_greeting(self, project: Project, user: UserProfile, db: Session) -> dict:
        """Generate a greeting when the user opens a project with no message."""
        recent = (
            db.query(ChatMessage)
            .filter_by(project_id=project.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        recent.reverse()

        recent_runs = (
            db.query(AgentRun)
            .filter_by(project_id=project.id)
            .order_by(AgentRun.created_at.desc())
            .limit(3)
            .all()
        )

        run_context = ""
        if recent_runs:
            run_context = "## Recent work in this project"
            for run in recent_runs:
                goal_snippet = (run.goal or "")[:200]
                result_snippet = (run.result_summary or "")[:300]
                run_context += f"\n- Goal: {goal_snippet}"
                if result_snippet:
                    run_context += f"\n  Result: {result_snippet}"
            greeting_instruction = (
                "Welcome them back briefly, remind them where things stand, "
                "and ask what they'd like to focus on next."
            )
        else:
            greeting_instruction = (
                "Greet them briefly and ask what they'd like help with. "
                "Don't present generic options — start a real conversation."
            )

        display_name = (
            project.name
            if project.name.lower() not in ("new task", "untitled")
            else "this new task"
        )

        instruction = f"""\
<run_context>
{run_context}
</run_context>

The user just opened {display_name}. {greeting_instruction}

Keep your greeting brief and conversational (1-2 sentences).
Don't include detailed research or tool recommendations yet.
Ask a genuine question to understand what they want to work on.
Do NOT mention the project name if it's generic like "this new task" — just greet them naturally.

Respond with JSON:
{{"message": "your greeting", "actions": []}}

Return ONLY the JSON object."""

        base_prompt = self._build_base_prompt(user, project, db)
        llm_messages = [{"role": m.role, "content": m.content} for m in recent]
        llm_messages.append({"role": "user", "content": instruction})

        raw = chat_messages(base_prompt, llm_messages, json_mode=True)
        result = parse_json(raw)

        result.setdefault("message", "")
        result.setdefault("actions", [])

        db.add(ChatMessage(
            project_id=project.id,
            role="assistant",
            content=result["message"],
            actions=result["actions"],
        ))
        db.commit()

        return {
            "message": result["message"],
            "actions": result["actions"],
            "blocks": [],
            "phase": None,
        }

    def _return_last_message(self, project: Project, db: Session) -> dict:
        """Return the last assistant message (no new user message)."""
        last = (
            db.query(ChatMessage)
            .filter_by(project_id=project.id, role="assistant")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if last:
            return {
                "message": last.content,
                "actions": last.actions or [],
                "blocks": last.blocks or [],
                "phase": last.phase,
            }
        return {"message": "", "actions": [], "blocks": [], "phase": None}

    def _build_base_prompt(self, user: UserProfile, project: Project, db: Session) -> str:
        """Build the system prompt with context and memory."""
        base = build_system_prompt(user, project)

        context_text = get_context_text(db, user.id, project_id=project.id)
        if context_text:
            base += f"\n\n{context_text}"

        memory = retrieve_insights(user.id, project.description or "", db)
        if memory:
            base += f"\n\n{memory}"

        return base

    def _build_user_context(self, user: UserProfile) -> str:
        """Build user context string for prompt injection."""
        parts = []
        if user.model_summary:
            parts.append(f"## About the user\n{user.model_summary}")
        if user.onboarding_info:
            try:
                info = json.loads(user.onboarding_info) if isinstance(user.onboarding_info, str) else user.onboarding_info
                if info.get("needs"):
                    parts.append(f"Known needs: {', '.join(info['needs'][:6])}")
                if info.get("goals"):
                    parts.append(f"Known goals: {', '.join(info['goals'][:6])}")
            except (json.JSONDecodeError, TypeError):
                pass
        return "\n".join(parts) if parts else "No prior context about this user."

    def _get_conversation_history(self, project_id: int, db: Session) -> list[dict]:
        """Load recent conversation history as message dicts."""
        recent = (
            db.query(ChatMessage)
            .filter_by(project_id=project_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        recent.reverse()
        return [{"role": m.role, "content": m.content} for m in recent]

    def _get_user_goal(self, project_id: int, db: Session) -> str:
        """Extract the user's original goal from the first user message."""
        first_msg = (
            db.query(ChatMessage)
            .filter_by(project_id=project_id, role="user")
            .order_by(ChatMessage.created_at.asc())
            .first()
        )
        return first_msg.content if first_msg else ""

    def _format_history(self, messages: list[dict]) -> str:
        """Format message history as readable text for prompt injection."""
        if not messages:
            return "No prior conversation."
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:])

    def _question_to_block(self, question: dict, index: int) -> list[dict]:
        """Convert a diagnostic question spec to a message block."""
        if isinstance(question, str):
            return [{
                "type": "input",
                "id": f"diagnostic_{index}",
                "prompt": question,
                "placeholder": "",
            }]

        q_type = question.get("type", "select")
        q_text = question.get("question", "")
        options = question.get("options", [])

        if q_type == "input" or not options:
            return [{
                "type": "input",
                "id": f"diagnostic_{index}",
                "prompt": q_text,
                "placeholder": "",
            }]

        return [{
            "type": "select",
            "id": f"diagnostic_{index}",
            "prompt": q_text,
            "options": [
                {"value": opt.lower().replace(" ", "_"), "label": opt}
                for opt in options
            ],
            "multi": False,
        }]


# Singleton
flow_engine = FlowEngine()
