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
        
        # Fetch additional context for insights generation
        user_goals = self.db.get_user_goals(user_id)
        recent_sessions = self.db.get_user_sessions(user_id)
        
        print(f"[TrajectoryUpdater] Found {len(user_goals)} goals in database for user {user_id[:8]}...")
        if user_goals:
            for g in user_goals:
                print(f"  - Goal {g['id']}: {g['goal_text'][:60]}...")
        
        # Get user profile to extract learner_model data even when there are no checkpoints
        user_profile = self.db.get_or_create_user(user_id)
        
        # Extract themes from recent sessions
        all_themes = []
        for session_obj in recent_sessions[:3]:  # Last 3 sessions
            schema_state = session_obj.schema_state if hasattr(session_obj, 'schema_state') else None
            if isinstance(schema_state, dict):
                themes = schema_state.get('conversational_themes', [])
                all_themes.extend([t.get('theme_seed', '') for t in themes if isinstance(t, dict)])
        
        # Fetch conversation history for each goal to generate insightful descriptions
        goals_with_history = []
        
        # Get all exploration sessions (including ended ones) - goals may have been discovered in past sessions
        all_exploration_sessions = [s for s in recent_sessions if getattr(s, 'session_type', None) == 'exploration']
        exploration_history = []
        if all_exploration_sessions:
            # Combine conversation history from all exploration sessions, most recent first
            # Sort by started_at if available, otherwise just use order from query
            for exp_session in all_exploration_sessions:
                history = getattr(exp_session, 'conversation_history', None) or []
                if history:
                    exploration_history.extend(history)
            # Limit to last 20 messages from exploration to avoid token bloat
            exploration_history = exploration_history[-20:]
        
        print(f"[TrajectoryUpdater] Found {len(all_exploration_sessions)} exploration sessions, total history length: {len(exploration_history)}")
        
        for g in user_goals:
            goal_id = g["id"]
            goal_data = {
                "goal_id": goal_id,
                "goal_text": g["goal_text"],
                "status": g["status"]
            }
            
            # Get conversation history from goal-specific sessions
            goal_sessions = self.db.list_sessions_for_goal(goal_id)
            goal_conversation_history = []
            for sess in goal_sessions:
                history = sess.get("conversation_history", [])
                if history:
                    goal_conversation_history.extend(history)
            
            print(f"[TrajectoryUpdater] Goal {goal_id} ({g['goal_text'][:50]}...): {len(goal_sessions)} sessions, {len(goal_conversation_history)} goal messages, {len(exploration_history)} exploration messages")
            
            # Include exploration conversation history (where goal was likely discovered)
            # Limit to last 10 messages to avoid token bloat
            all_history = exploration_history + goal_conversation_history
            if all_history:
                # Take last 10 messages total, prioritizing goal sessions
                if len(goal_conversation_history) >= 10:
                    goal_data["conversation_history"] = goal_conversation_history[-10:]
                elif len(goal_conversation_history) > 0:
                    # Mix exploration and goal history
                    remaining = 10 - len(goal_conversation_history)
                    if remaining > 0 and exploration_history:
                        goal_data["conversation_history"] = goal_conversation_history + exploration_history[-remaining:]
                    else:
                        goal_data["conversation_history"] = goal_conversation_history
                elif exploration_history:
                    # Only exploration history available
                    goal_data["conversation_history"] = exploration_history[-10:]
                
                print(f"[TrajectoryUpdater] Goal {goal_id}: Including {len(goal_data.get('conversation_history', []))} messages in context")
            else:
                print(f"[TrajectoryUpdater] Goal {goal_id}: WARNING - No conversation history found!")
            
            goals_with_history.append(goal_data)
        
        context = {
            "goals": goals_with_history,
            "themes": list(set(all_themes))[:10],  # Unique themes, top 10
            "user_profile": {
                "curiosity_type": user_profile.curiosity_type if hasattr(user_profile, 'curiosity_type') else None,
                "pacing_preference": user_profile.pacing_preference if hasattr(user_profile, 'pacing_preference') else None,
                "uncertainty_tolerance": user_profile.uncertainty_tolerance if hasattr(user_profile, 'uncertainty_tolerance') else None,
                "entry_mode": user_profile.entry_mode if hasattr(user_profile, 'entry_mode') else None,
                "motivation_profile": user_profile.motivation_profile if hasattr(user_profile, 'motivation_profile') else None,
            },
            "exploration_conversation_summary": self._summarize_conversation(exploration_history) if exploration_history else None
        }
        
        # If no new checkpoints, still try to populate from user profile and ensure goals are included
        if not new_checkpoints:
            # Check if we need to update: dashboard is empty, learner_model is empty, OR goals exist but aren't in dashboard
            existing_goals_in_dashboard = dashboard_state.get("goals", []) if dashboard_state else []
            goals_exist_in_db = len(user_goals) > 0
            goals_missing = goals_exist_in_db and len(existing_goals_in_dashboard) == 0
            
            needs_update = (
                not dashboard_state or 
                not dashboard_state.get("learner_model") or 
                all(not v or (isinstance(v, list) and len(v) == 0) for v in (dashboard_state.get("learner_model") or {}).values()) or
                goals_missing
            )
            
            if needs_update:
                # Use LLM to extract initial learner_model from user profile and ensure goals are included
                print(f"[TrajectoryUpdater] No new checkpoints but needs update (goals_missing={goals_missing}, goals_in_db={len(user_goals)})")
                prompt = self._build_prompt(
                    user_id=user_id,
                    previous_dashboard=dashboard_state or {},
                    new_checkpoints=[],
                    context=context,
                )
                
                updated = self.llm.chat_with_json(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.2,
                    max_tokens=2500,
                )

                if isinstance(updated, dict):
                    # Fix goal field names: LLM often returns "id" but schema expects "goal_id"
                    if "goals" in updated and isinstance(updated["goals"], list):
                        for goal in updated["goals"]:
                            if isinstance(goal, dict) and "id" in goal and "goal_id" not in goal:
                                goal["goal_id"] = goal.pop("id")
                    
                    # Safety check: Ensure all goals from context are included
                    if len(user_goals) > 0:
                        goals_in_output = updated.get("goals", [])
                        goal_ids_in_output = {g.get("goal_id") for g in goals_in_output if isinstance(g, dict)}
                        goal_ids_in_db = {g["id"] for g in user_goals}
                        missing_goal_ids = goal_ids_in_db - goal_ids_in_output
                        
                        if missing_goal_ids:
                            print(f"[TrajectoryUpdater] WARNING: LLM omitted {len(missing_goal_ids)} goals from output, adding them back")
                            # Add missing goals with basic structure
                            for goal_data in user_goals:
                                if goal_data["id"] in missing_goal_ids:
                                    goals_in_output.append({
                                        "goal_id": goal_data["id"],
                                        "goal_text": goal_data["goal_text"],
                                        "status": goal_data.get("status", "active"),
                                        "momentum": "inactive",
                                        "last_activity_at": None,
                                        "learning_summary": "",
                                        "next_suggested_move": ""
                                    })
                            updated["goals"] = goals_in_output

                    updated["user_id"] = user_id
                    updated["version"] = int(updated.get("version") or 1)
                    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
                    validated = LearnerTrajectoryDashboard.model_validate(updated).model_dump()
                    self.db.save_learner_trajectory(user_id, validated, last_checkpoint_id=last_checkpoint_id)
                    return validated
            
            # If dashboard exists but goals are missing, force update to include them
            if goals_missing and dashboard_state:
                print(f"[TrajectoryUpdater] Dashboard exists but missing {len(user_goals)} goals - forcing update to include them")
                # Force update to include goals
                prompt = self._build_prompt(
                    user_id=user_id,
                    previous_dashboard=dashboard_state,
                    new_checkpoints=[],
                    context=context,
                )
                updated = self.llm.chat_with_json(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.2,
                    max_tokens=2500,
                )
                if isinstance(updated, dict):
                    # Fix goal field names
                    if "goals" in updated and isinstance(updated["goals"], list):
                        for goal in updated["goals"]:
                            if isinstance(goal, dict) and "id" in goal and "goal_id" not in goal:
                                goal["goal_id"] = goal.pop("id")
                    
                    # Safety check: Ensure all goals from context are included
                    goals_in_output = updated.get("goals", [])
                    if len(user_goals) > 0:
                        goal_ids_in_output = {g.get("goal_id") for g in goals_in_output if isinstance(g, dict)}
                        goal_ids_in_db = {g["id"] for g in user_goals}
                        missing_goal_ids = goal_ids_in_db - goal_ids_in_output
                        
                        if missing_goal_ids:
                            print(f"[TrajectoryUpdater] WARNING: LLM omitted {len(missing_goal_ids)} goals, adding them back")
                            for goal_data in user_goals:
                                if goal_data["id"] in missing_goal_ids:
                                    goals_in_output.append({
                                        "goal_id": goal_data["id"],
                                        "goal_text": goal_data["goal_text"],
                                        "status": goal_data.get("status", "active"),
                                        "momentum": "inactive",
                                        "last_activity_at": None,
                                        "learning_summary": "",
                                        "next_suggested_move": ""
                                    })
                    
                    # Merge with existing dashboard state
                    ensured = LearnerTrajectoryDashboard.model_validate(dashboard_state).model_dump()
                    ensured.update({
                        "goals": goals_in_output,
                        "insights": updated.get("insights", ensured.get("insights", "")),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })
                    self.db.save_learner_trajectory(user_id, ensured, last_checkpoint_id=last_checkpoint_id)
                    return ensured
            
            # Ensure stable shape even for brand-new users
            ensured = LearnerTrajectoryDashboard.model_validate(dashboard_state or {"user_id": user_id}).model_dump()
            if not dashboard_state:
                self.db.save_learner_trajectory(user_id, ensured, last_checkpoint_id=last_checkpoint_id)
            return ensured

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

        # Fix goal field names: LLM often returns "id" but schema expects "goal_id"
        if "goals" in updated and isinstance(updated["goals"], list):
            for goal in updated["goals"]:
                if isinstance(goal, dict) and "id" in goal and "goal_id" not in goal:
                    goal["goal_id"] = goal.pop("id")

        # Safety check: Ensure all goals from context are included (LLM might have omitted them)
        if len(user_goals) > 0:
            goals_in_output = updated.get("goals", [])
            goal_ids_in_output = {g.get("goal_id") for g in goals_in_output if isinstance(g, dict)}
            goal_ids_in_db = {g["id"] for g in user_goals}
            missing_goal_ids = goal_ids_in_db - goal_ids_in_output
            
            if missing_goal_ids:
                print(f"[TrajectoryUpdater] WARNING: LLM omitted {len(missing_goal_ids)} goals from output, adding them back")
                # Add missing goals with basic structure
                for goal_data in user_goals:
                    if goal_data["id"] in missing_goal_ids:
                        goals_in_output.append({
                            "goal_id": goal_data["id"],
                            "goal_text": goal_data["goal_text"],
                            "status": goal_data.get("status", "active"),
                            "momentum": "inactive",  # Default since we don't have activity data
                            "last_activity_at": None,
                            "learning_summary": "",  # Will be populated by LLM on next refresh
                            "next_suggested_move": ""
                        })
                updated["goals"] = goals_in_output

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
    
    def _summarize_conversation(self, conversation_history: list, max_length: int = 500) -> str:
        """Create a concise summary of conversation history for context."""
        if not conversation_history:
            return ""
        
        # Extract key user messages (their motivations, questions, interests)
        user_messages = [msg.get("content", "") for msg in conversation_history if msg.get("role") == "user"]
        
        # Take first and last few user messages to capture evolution
        if len(user_messages) <= 3:
            summary = " ".join(user_messages)
        else:
            summary = " ".join(user_messages[:2] + user_messages[-2:])
        
        # Truncate if too long
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary


