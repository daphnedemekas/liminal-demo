"""Incremental updater for the Learner Trajectory dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.database.manager import DatabaseManager
from src.llm_client import LLMClient
from src.schema.trajectory_schema import LearnerTrajectoryDashboard


class TrajectoryUpdater:
    """
    Incrementally updates a user's trajectory dashboard JSON using new checkpoints.

    This is designed to be:
    - stable (always returns a full dashboard object)
    - sparse (only updates when there are new checkpoints)
    - incremental (takes previous dashboard as input)
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.llm = LLMClient()

    def refresh(self, user_id: str, model: str = "cerebras:llama-3.3-70b") -> Dict[str, Any]:
        """Refresh dashboard state from checkpoints and persist; returns updated dashboard JSON."""
        traj = self.db.get_or_create_learner_trajectory(user_id)
        dashboard_state = traj.get("dashboard_state") or {}
        last_checkpoint_id = traj.get("last_checkpoint_id")

        new_checkpoints = self.db.list_trajectory_checkpoints(user_id=user_id, since_id=last_checkpoint_id, limit=500)
        if not new_checkpoints:
            # Ensure stable shape even for brand-new users
            ensured = LearnerTrajectoryDashboard.model_validate(dashboard_state or {"user_id": user_id}).model_dump()
            if not dashboard_state:
                self.db.save_learner_trajectory(user_id, ensured, last_checkpoint_id=last_checkpoint_id)
            return ensured

        # Fetch additional context for insights generation
        user_goals = self.db.get_user_goals(user_id)
        recent_sessions = self.db.get_user_sessions(user_id)
        
        # Extract themes from recent sessions
        all_themes = []
        for session in recent_sessions[:3]:  # Last 3 sessions
            schema_state = session.schema_state if hasattr(session, 'schema_state') else None
            if isinstance(schema_state, dict):
                themes = schema_state.get('conversational_themes', [])
                all_themes.extend([t.get('theme_seed', '') for t in themes if isinstance(t, dict)])
        
        context = {
            "goals": [{"id": g["id"], "text": g["goal_text"], "status": g["status"]} for g in user_goals],
            "themes": list(set(all_themes))[:10]  # Unique themes, top 10
        }

        prompt = self._build_prompt(
            user_id=user_id,
            previous_dashboard=dashboard_state,
            new_checkpoints=new_checkpoints,
            context=context,
        )

        updated = self.llm.chat_with_json(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.2,
            max_tokens=2500,
        )
        
        print(f"[TrajectoryUpdater] LLM returned insights: '{updated.get('insights', '(missing)')[:100]}...'")

        if not isinstance(updated, dict):
            raise ValueError(f"LLM returned non-dict response: {type(updated)}")

        # Enforce required fields + stable shape
        updated["user_id"] = user_id
        updated["version"] = int(updated.get("version") or 1)
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()

        validated = LearnerTrajectoryDashboard.model_validate(updated).model_dump()

        new_last_id = new_checkpoints[-1]["id"]
        self.db.save_learner_trajectory(user_id, validated, last_checkpoint_id=new_last_id)
        return validated

    def _build_prompt(self, *, user_id: str, previous_dashboard: Dict[str, Any], new_checkpoints: list, context: Dict[str, Any] = None) -> str:
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "trajectory" / "update_trajectory.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Required prompt file missing: {prompt_path}")
        template = prompt_path.read_text()

        context = context or {}
        return template.format(
            user_id=user_id,
            previous_dashboard_json=self._safe_json(previous_dashboard),
            new_checkpoints_json=self._safe_json(new_checkpoints),
            context_json=self._safe_json(context),
        )

    def _safe_json(self, obj: Any) -> str:
        import json
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


