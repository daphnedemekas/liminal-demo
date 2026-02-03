"""Onboarding orchestrator: narrowing Q&A, signal extraction, project suggestions.

Flow:
1. quick_context — user picks from multiple-choice options (what brings you here)
2. deeper_qa — LLM asks adaptive follow-up questions based on signals gathered so far
3. exploring — open conversation to discover what the user needs help with
4. complete — onboarding done, suggested projects generated

Each phase is skippable. The user can jump straight to using the app at any time.
"""

from __future__ import annotations

import json
import logging

from backend.database import OnboardingState, UserProfile, Project, get_session_factory
from backend.services.llm import chat_json

logger = logging.getLogger(__name__)


# The predefined quick-context options
QUICK_CONTEXT_OPTIONS = [
    {"id": "business", "label": "Running a business", "icon": "briefcase"},
    {"id": "developer", "label": "Building software", "icon": "code"},
    {"id": "student", "label": "Studying / learning", "icon": "book"},
    {"id": "researcher", "label": "Research & analysis", "icon": "search"},
    {"id": "personal", "label": "Managing personal life", "icon": "home"},
    {"id": "exploring", "label": "Just exploring", "icon": "compass"},
]


class OnboardingOrchestrator:
    """Drives the onboarding conversation and extracts signals."""

    def get_state(self, user_id: str) -> dict:
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            if not state:
                return {"phase": "quick_context", "gathered_signals": {}, "suggested_projects": []}
            return {
                "phase": state.phase,
                "gathered_signals": state.gathered_signals or {},
                "pending_questions": state.pending_questions or [],
                "suggested_projects": state.suggested_projects or [],
                "conversation_history": state.conversation_history or [],
            }
        finally:
            session.close()

    def submit_quick_context(self, user_id: str, selected_ids: list[str]) -> dict:
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not state or not user:
                raise ValueError("User or onboarding state not found")

            labels = {o["id"]: o["label"] for o in QUICK_CONTEXT_OPTIONS}
            selected_labels = [labels.get(sid, sid) for sid in selected_ids]

            signals = state.gathered_signals or {}
            signals["context_types"] = selected_ids
            signals["context_labels"] = selected_labels
            state.gathered_signals = dict(signals)  # force new object for SQLAlchemy mutation detection

            if selected_ids:
                type_map = {"business": "business", "developer": "developer",
                            "student": "student", "researcher": "researcher",
                            "personal": "individual", "exploring": "exploring"}
                user.user_type = type_map.get(selected_ids[0], "exploring")

            state.phase = "deeper_qa"
            session.commit()

            return {"phase": state.phase, "gathered_signals": signals}
        finally:
            session.close()

    async def generate_next_question(self, user_id: str) -> dict:
        """Generate a single adaptive question based on everything gathered so far."""
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not state or not user:
                raise ValueError("User or onboarding state not found")

            signals = state.gathered_signals or {}
            history = state.conversation_history or []
            prompt = self._build_question_prompt(user.name, signals, history)

            question = chat_json(prompt)

            # Store the question in history so the next question knows what was already asked
            history.append({"role": "assistant", "content": question["question"]})
            state.conversation_history = list(history)  # force new object for SQLAlchemy mutation detection
            state.pending_questions = [question]
            session.commit()
            return question
        finally:
            session.close()

    async def process_answer(self, user_id: str, answer: str) -> dict:
        """Process answer, extract signals, decide if we have enough to suggest."""
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not state or not user:
                raise ValueError("User or onboarding state not found")

            history = state.conversation_history or []
            history.append({"role": "user", "content": answer})
            state.conversation_history = list(history)  # force new object for SQLAlchemy mutation detection

            signals = await self._extract_signals(user.name, state.gathered_signals or {}, history)
            state.gathered_signals = dict(signals)  # force new object for SQLAlchemy mutation detection

            # After 2+ answers, we have enough to make suggestions
            answer_count = sum(1 for m in history if m["role"] == "user")
            ready_for_suggestions = answer_count >= 2

            session.commit()

            return {
                "gathered_signals": signals,
                "conversation_history": history,
                "ready_for_suggestions": ready_for_suggestions,
            }
        finally:
            session.close()

    async def generate_suggestions(self, user_id: str) -> list[dict]:
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not state or not user:
                raise ValueError("User or onboarding state not found")

            signals = state.gathered_signals or {}
            history = state.conversation_history or []
            prompt = self._build_suggestion_prompt(user.name, signals, history)

            suggestions = chat_json(prompt)

            state.suggested_projects = suggestions
            session.commit()
            return suggestions
        finally:
            session.close()

    def accept_suggestions(self, user_id: str, suggestion_indices: list[int]) -> list[dict]:
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not state or not user:
                raise ValueError("User or onboarding state not found")

            suggestions = state.suggested_projects or []
            created = []

            for idx in suggestion_indices:
                if 0 <= idx < len(suggestions):
                    s = suggestions[idx]
                    project = Project(
                        user_id=user_id,
                        name=s.get("name", "New project"),
                        description=s.get("description", ""),
                        suggested_by_system=True,
                    )
                    session.add(project)
                    session.flush()
                    created.append({"id": project.id, "name": project.name, "description": project.description})

            state.phase = "complete"
            user.onboarding_complete = True
            user.model_summary = self._summarize_user(user.name, state.gathered_signals or {}, state.conversation_history or [])
            user.onboarding_info = json.dumps(state.gathered_signals or {})
            session.commit()
            return created
        finally:
            session.close()

    def skip_onboarding(self, user_id: str):
        session = get_session_factory()()
        try:
            state = session.query(OnboardingState).filter_by(user_id=user_id).first()
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if state:
                state.phase = "complete"
            if user:
                user.onboarding_complete = True
            session.commit()
        finally:
            session.close()

    # ── Prompt builders ──────────────────────────────────────────────

    def _build_question_prompt(self, name: str, signals: dict, history: list) -> str:
        context_parts = [f"User name: {name}"]
        if signals.get("context_labels"):
            context_parts.append(f"They're interested in: {', '.join(signals['context_labels'])}")
        if history:
            context_parts.append("Conversation so far:")
            for msg in history[-6:]:
                context_parts.append(f"  {msg['role']}: {msg['content']}")

        return f"""You are an onboarding assistant for Envisage, a personal AI assistant that helps people with anything — research, planning, business tasks, home projects, learning, organizing, and more.

Generate exactly ONE follow-up question to learn more about what this user needs help with.

Rules:
- Be conversational and warm
- NEVER ask for anything the user already told you — read the conversation carefully
- Ask about a NEW dimension you don't already know (what's on their plate, what frustrates them, what they wish they had help with, what takes too long)
- Be specific, not generic

{chr(10).join(context_parts)}

Respond with a single JSON object with "question" and "hint". Example:
{{"question": "What's taking up most of your time this week?", "hint": "e.g., managing emails, researching vendors, planning meals..."}}

Return ONLY the JSON object, no other text."""

    def _build_suggestion_prompt(self, name: str, signals: dict, history: list) -> str:
        context_parts = [f"User name: {name}"]
        if signals.get("context_labels"):
            context_parts.append(f"Interests: {', '.join(signals['context_labels'])}")
        for key, val in signals.items():
            if key not in ("context_types", "context_labels") and val:
                context_parts.append(f"{key}: {val}")
        if history:
            context_parts.append("Conversation:")
            for msg in history[-8:]:
                context_parts.append(f"  {msg['role']}: {msg['content']}")

        return f"""You are Envisage, a personal AI assistant. Based on everything you know about this user, suggest 2-3 PROJECT AREAS you could help them with.

{chr(10).join(context_parts)}

IMPORTANT — each suggestion should be a BROAD project, not a single task. Think about how a user would want to organize their work:
- GOOD: "Kitchen Renovation Planner" (encompasses research, budgeting, sourcing, scheduling)
- BAD: "Tile price comparison" (too narrow — that's one task within a project)
- GOOD: "Job Search Command Center" (resume, applications, interview prep, company research)
- BAD: "Resume tailoring" (too narrow — that's one task within a project)

Each project should:
- Bundle related tasks the user would naturally group together
- Be something the AI can actively work on over multiple sessions
- Have a clear scope but room for the AI to proactively do useful things within it

Keep it to 2-3 suggestions. Fewer, broader projects are better than many narrow ones.

For the "description", write 1-2 sentences from the AI's perspective explaining what it would proactively do: "I'll research X, compare Y, draft Z, and keep everything organized for you."

Respond with a JSON array of objects with "name" (short title, <60 chars) and "description". Return ONLY the JSON array."""

    def _summarize_user(self, name: str, signals: dict, history: list) -> str:
        """Use LLM to generate a rich user summary from onboarding signals."""
        from backend.services.llm import chat as llm_chat

        prompt = f"""Write a concise profile summary (3-5 sentences) of this person based on their onboarding conversation. This will be used by an AI assistant to personalize its help.

Name: {name}
Signals: {json.dumps(signals)}
Conversation:
{chr(10).join(f"  {m['role']}: {m['content']}" for m in history[-8:])}

Write in third person. Focus on: what they do, what they need help with, what frustrates them, and their goals. Be specific, not generic. Return ONLY the summary text, no JSON."""

        try:
            return llm_chat(prompt)
        except Exception:
            # Fallback to simple summary
            parts = [name]
            if signals.get("context_labels"):
                parts.append(f"interested in {', '.join(signals['context_labels'])}")
            if signals.get("needs"):
                parts.append(f"needs help with: {', '.join(signals['needs'][:5])}")
            if signals.get("goals"):
                parts.append(f"goals: {', '.join(signals['goals'][:3])}")
            return ". ".join(parts)

    async def _extract_signals(self, name: str, existing_signals: dict, history: list) -> dict:
        prompt = f"""You are analyzing an onboarding conversation for Envisage, a personal AI assistant.

User: {name}
Existing signals: {json.dumps(existing_signals)}
Recent conversation:
{chr(10).join(f"  {m['role']}: {m['content']}" for m in history[-6:])}

Extract key signals about this user. Return a JSON object that MERGES with the existing signals. Include fields like:
- "needs": list of specific things they need help with
- "pain_points": what frustrates them or takes too much time
- "goals": what they're trying to achieve
- "domain_knowledge": areas they know well vs areas they need help
- Keep all existing signal fields too

Return ONLY a JSON object, no other text."""

        result = chat_json(prompt)
        return {**existing_signals, **result}


onboarding = OnboardingOrchestrator()
