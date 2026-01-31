"""User model service: infers and updates preferences from interactions.

Observes user behavior (run topics, involvement choices, feedback) and
periodically updates the user's model_summary, known_domains, and preferences.
"""

import json
import logging

from backend.database import UserProfile, AgentRun, get_session_factory
from backend.services.llm import chat_json

logger = logging.getLogger(__name__)


class UserModelService:
    """Infers user preferences and knowledge from their interactions."""

    async def update_model(self, user_id: str):
        """Re-analyze all user data and update the model summary."""
        session = get_session_factory()()
        try:
            user = session.query(UserProfile).filter_by(id=user_id).first()
            if not user:
                return

            runs = session.query(AgentRun).filter_by(user_id=user_id).order_by(AgentRun.created_at.desc()).limit(20).all()

            if not runs:
                return

            run_summaries = [
                f"- {r.goal[:100]} (status: {r.status})"
                for r in runs
            ]

            prompt = f"""Analyze this user's interactions with Liminal (a personal AI assistant) and produce a brief profile.

User: {user.name}
Type: {user.user_type}
Onboarding info: {user.onboarding_info or 'none'}
Existing model: {user.model_summary or 'none'}
Known domains: {json.dumps(user.known_domains or {})}

Recent tasks:
{chr(10).join(run_summaries)}

Return a JSON object with:
- "summary": 2-3 sentence profile of the user (who they are, what they need)
- "known_domains": object mapping domain names to familiarity (novice/intermediate/expert)
- "suggested_involvement": "hands_off" | "check_ins" | "involved" based on observed behavior
- "suggested_explanation": "just_results" | "brief_summary" | "show_your_work"

Return ONLY the JSON object."""

            result = chat_json(prompt)

            user.model_summary = result.get("summary", user.model_summary)
            if result.get("known_domains"):
                user.known_domains = result["known_domains"]

            session.commit()

        except Exception as e:
            logger.exception(f"Failed to update user model for {user_id}: {e}")
        finally:
            session.close()


user_model_service = UserModelService()
