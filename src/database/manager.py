"""Database manager for user profiles and sessions."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import os

from .models import (
    Base,
    UserProfile,
    ConversationSession,
    Signal,
    UserGoal,
    FeedItem,
    LearnerTrajectory,
    TrajectoryCheckpoint,
)


class DatabaseManager:
    """Manages database operations for user profiles, sessions, and signals."""

    def __init__(self, db_path: str = "data/liminal.db", database_url: Optional[str] = None):
        """
        Initialize database manager.

        Priority:
        1. DATABASE_URL (Postgres) - Used in production (Railway, etc.)
        2. db_path (SQLite) - Used for local development only

        Args:
            db_path: Path to SQLite database file (only used if DATABASE_URL is not set)
            database_url: PostgreSQL connection URL (e.g., from Railway DATABASE_URL env var)
        """
        # Check for DATABASE_URL environment variable first (Railway Postgres)
        database_url = database_url or os.getenv("DATABASE_URL")
        
        if database_url:
            # PostgreSQL connection (Railway or other Postgres provider)
            # Railway provides DATABASE_URL in format: postgres://user:password@host:port/dbname
            # SQLAlchemy needs postgresql:// (not postgres://) for newer versions
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            
            print(f"[Database] Attempting PostgreSQL connection from DATABASE_URL")
            try:
                # Add fast timeout to prevent hanging on connection attempts
                # connect_args with connect_timeout prevents long waits if Postgres isn't available
                self.engine = create_engine(
                    database_url, 
                    echo=False, 
                    pool_pre_ping=True,
                    connect_args={"connect_timeout": 3}  # 3 second timeout - fail fast
                )
                # Test connection with timeout
                from sqlalchemy import text
                
                # Use a quick connection test (connect_timeout in connect_args handles timeout)
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                print(f"[Database] PostgreSQL connection test successful")
                
                # Create all tables
                Base.metadata.create_all(self.engine)
                print(f"[Database] PostgreSQL tables created/verified successfully")
                
            except Exception as e:
                print(f"[Database] ERROR: Failed to connect to PostgreSQL: {e}")
                print(f"[Database] This might mean:")
                print(f"[Database]   1. Postgres service isn't connected in Railway")
                print(f"[Database]   2. Services are in different regions")
                print(f"[Database]   3. Internal DNS not resolving yet")
                print(f"[Database] Falling back to SQLite immediately...")
                # Fall back to SQLite if Postgres connection fails
                database_url = None  # Clear so we use SQLite path below
        else:
            print(f"[Database] No DATABASE_URL found, using SQLite")
        
        # Use SQLite if no DATABASE_URL or if Postgres failed
        if not database_url:
            # SQLite fallback for local development or when Postgres unavailable
            # Ensure data directory exists
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            print(f"[Database] Using SQLite database at {db_path}")
            self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
            
            # Create all tables for SQLite
            try:
                Base.metadata.create_all(self.engine)
                print(f"[Database] SQLite tables created/verified successfully")
            except Exception as e:
                print(f"[Database] ERROR: Failed to create SQLite tables: {e}")
                raise
        
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    # ============================================
    # Learner Trajectory (cross-phase dashboard)
    # ============================================

    def get_or_create_learner_trajectory(self, user_id: str) -> Dict[str, Any]:
        """Get or create the canonical learner trajectory dashboard state for a user."""
        session = self._get_session()
        try:
            traj = session.query(LearnerTrajectory).filter_by(user_id=user_id).first()
            if not traj:
                traj = LearnerTrajectory(
                    user_id=user_id,
                    dashboard_state=self._default_trajectory_state(user_id),
                    last_checkpoint_id=None,
                )
                session.add(traj)
                session.commit()
                session.refresh(traj)
            return {
                "user_id": traj.user_id,
                "dashboard_state": traj.dashboard_state or self._default_trajectory_state(user_id),
                "last_checkpoint_id": traj.last_checkpoint_id,
                "updated_at": traj.updated_at.isoformat() if traj.updated_at else None,
            }
        finally:
            session.close()

    def save_learner_trajectory(self, user_id: str, dashboard_state: Dict[str, Any], last_checkpoint_id: Optional[int] = None):
        """Upsert learner trajectory state."""
        session = self._get_session()
        try:
            traj = session.query(LearnerTrajectory).filter_by(user_id=user_id).first()
            if not traj:
                traj = LearnerTrajectory(user_id=user_id, dashboard_state=dashboard_state, last_checkpoint_id=last_checkpoint_id)
                session.add(traj)
            else:
                traj.dashboard_state = dashboard_state
                if last_checkpoint_id is not None:
                    traj.last_checkpoint_id = last_checkpoint_id
            session.commit()
        finally:
            session.close()

    def list_trajectory_checkpoints(self, user_id: str, since_id: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """List checkpoints for a user (optionally only those after a given checkpoint id)."""
        session = self._get_session()
        try:
            query = session.query(TrajectoryCheckpoint).filter_by(user_id=user_id).order_by(TrajectoryCheckpoint.id.asc())
            if since_id is not None:
                query = query.filter(TrajectoryCheckpoint.id > since_id)
            query = query.limit(limit)
            rows = query.all()
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "session_id": r.session_id,
                    "session_type": r.session_type,
                    "goal_id": r.goal_id,
                    "teaching_candidate_id": r.teaching_candidate_id,
                    "turn_index": r.turn_index,
                    "metrics": r.metrics or {},
                    "events": r.events or [],
                    "source_summary": r.source_summary,
                }
                for r in rows
            ]
        finally:
            session.close()

    def get_latest_trajectory_checkpoint(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest checkpoint for a user (by id)."""
        session = self._get_session()
        try:
            r = (
                session.query(TrajectoryCheckpoint)
                .filter_by(user_id=user_id)
                .order_by(TrajectoryCheckpoint.id.desc())
                .first()
            )
            if not r:
                return None
            return {
                "id": r.id,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "session_id": r.session_id,
                "session_type": r.session_type,
                "goal_id": r.goal_id,
                "teaching_candidate_id": r.teaching_candidate_id,
                "turn_index": r.turn_index,
                "metrics": r.metrics or {},
                "events": r.events or [],
                "source_summary": r.source_summary,
            }
        finally:
            session.close()

    def write_trajectory_checkpoint(self, checkpoint: Dict[str, Any]) -> int:
        """Write a new trajectory checkpoint; returns checkpoint id."""
        session = self._get_session()
        try:
            row = TrajectoryCheckpoint(
                user_id=checkpoint["user_id"],
                session_id=checkpoint.get("session_id"),
                session_type=checkpoint.get("session_type"),
                goal_id=checkpoint.get("goal_id"),
                teaching_candidate_id=checkpoint.get("teaching_candidate_id"),
                turn_index=checkpoint.get("turn_index"),
                metrics=checkpoint.get("metrics") or {},
                events=checkpoint.get("events") or [],
                source_summary=checkpoint.get("source_summary"),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        finally:
            session.close()

    def maybe_write_trajectory_checkpoint(
        self,
        *,
        user_id: str,
        session_id: Optional[str],
        session_type: Optional[str],
        goal_id: Optional[int],
        teaching_candidate_id: Optional[int],
        schema_state: Optional[Dict[str, Any]],
        conversation_history: Optional[list],
        turn_index: Optional[int] = None,
    ) -> Optional[int]:
        """
        Emit a sparse checkpoint every ~10 user turns and on significant change triggers.

        V1 heuristic: cadence + basic deltas on a few stable fields (confidence, entry_mode, pacing, uncertainty).
        """
        if not user_id:
            return None

        turns_elapsed = None
        if isinstance(schema_state, dict):
            turns_elapsed = schema_state.get("turns_elapsed")
            if turns_elapsed is None:
                turns_elapsed = schema_state.get("interview_state", {}).get("turns_elapsed")
        if turn_index is None and isinstance(turns_elapsed, int):
            turn_index = turns_elapsed

        # Determine if cadence checkpoint should fire
        cadence_fire = isinstance(turn_index, int) and turn_index > 0 and (turn_index % 10 == 0)

        # Pull last checkpoint metrics for simple drift detection
        last = None
        try:
            last = self.get_latest_trajectory_checkpoint(user_id=user_id)
        except Exception:
            last = None

        # Force first checkpoint at turn 1 or 2 to establish baseline
        is_first_checkpoint = last is None and isinstance(turn_index, int) and turn_index <= 2

        metrics = self._extract_trajectory_metrics(schema_state=schema_state, conversation_history=conversation_history)
        events = self._detect_trajectory_events(prev_metrics=(last.get("metrics") if last else None), metrics=metrics)

        should_write = cadence_fire or (len(events) > 0) or is_first_checkpoint
        if not should_write:
            return None
        
        # Debug logging
        if is_first_checkpoint:
            print(f"[Trajectory] Writing first checkpoint for user {user_id[:8]}... at turn {turn_index}")

        return self.write_trajectory_checkpoint(
            {
                "user_id": user_id,
                "session_id": session_id,
                "session_type": session_type,
                "goal_id": goal_id,
                "teaching_candidate_id": teaching_candidate_id,
                "turn_index": turn_index,
                "metrics": metrics,
                "events": events,
                "source_summary": None,
            }
        )

    def _default_trajectory_state(self, user_id: str) -> Dict[str, Any]:
        """Default dashboard state payload (stable shape for frontend)."""
        return {
            "version": 1,
            "user_id": user_id,
            "updated_at": None,
            "highlights": [],
            "goals": [],
            "engagement": {
                "sessions_per_week": [],
                "turns_per_session": [],
                "mode_mix": [],
            },
            "learner_model": {
                "stability": {"confidence_in_profile": [], "confidence_in_target": []},
                "entry_mode": [],
                "pacing_preference": [],
                "uncertainty_tolerance": [],
                "curiosity_type": [],
                "motivation_profile": [],
            },
        }

    def _extract_trajectory_metrics(self, *, schema_state: Optional[Dict[str, Any]], conversation_history: Optional[list]) -> Dict[str, Any]:
        """Extract compact, chart-friendly metrics from a session schema snapshot."""
        metrics: Dict[str, Any] = {}
        if not isinstance(schema_state, dict):
            return metrics

        # Try to support both DiscoverySchema and TeachingSchema snapshots.
        interview_state = schema_state.get("interview_state") or {}
        user_profile = schema_state.get("user_profile") or {}
        curriculum_plan = schema_state.get("curriculum_plan") or {}

        def _safe_get(d: dict, path: List[str]):
            cur = d
            for p in path:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(p)
            return cur

        # Discovery confidence
        metrics["confidence_in_profile"] = interview_state.get("confidence_in_profile")
        metrics["confidence_in_target"] = interview_state.get("confidence_in_target")

        # Core learner traits
        metrics["entry_mode"] = user_profile.get("entry_mode")
        metrics["pacing_preference"] = _safe_get(user_profile, ["pacing_preference", "value"])
        metrics["pacing_preference_confidence"] = _safe_get(user_profile, ["pacing_preference", "confidence"])
        metrics["uncertainty_tolerance"] = _safe_get(user_profile, ["uncertainty_tolerance", "value"])
        metrics["uncertainty_tolerance_confidence"] = _safe_get(user_profile, ["uncertainty_tolerance", "confidence"])
        metrics["curiosity_type"] = _safe_get(user_profile, ["curiosity_type", "value"])
        metrics["curiosity_type_confidence"] = _safe_get(user_profile, ["curiosity_type", "confidence"])
        metrics["motivation_profile"] = user_profile.get("motivation_profile")

        # Lightweight engagement window (current session only)
        if isinstance(conversation_history, list):
            user_msgs = [m for m in conversation_history if isinstance(m, dict) and m.get("role") == "user"]
            last_user = user_msgs[-1].get("content", "") if user_msgs else ""
            metrics["session_turns"] = len(user_msgs)
            metrics["last_user_msg_len"] = len(last_user) if isinstance(last_user, str) else 0
            metrics["last_user_question_mark"] = ("?" in last_user) if isinstance(last_user, str) else False

        # Teaching metrics (if present)
        if "understanding_markers" in schema_state:
            metrics["teaching_turns_elapsed"] = schema_state.get("turns_elapsed")
            metrics["teaching_current_step_index"] = schema_state.get("current_step_index")
            completed = (curriculum_plan.get("completed_step_ids") or []) if isinstance(curriculum_plan, dict) else []
            steps = (curriculum_plan.get("steps") or []) if isinstance(curriculum_plan, dict) else []
            metrics["teaching_steps_completed"] = len(completed) if isinstance(completed, list) else 0
            metrics["teaching_steps_total"] = len(steps) if isinstance(steps, list) else 0

            # Marker levels as a compact dict: {marker_id: level}
            marker_levels = {}
            markers = schema_state.get("understanding_markers") or []
            if isinstance(markers, list):
                for m in markers:
                    if isinstance(m, dict) and m.get("id"):
                        marker_levels[m["id"]] = m.get("level")
            metrics["teaching_marker_levels"] = marker_levels

            # NEW: Add aggregated metrics from understanding markers
            if marker_levels:
                try:
                    from src.trajectory.metrics import compute_all_aggregates
                    aggregates = compute_all_aggregates(marker_levels)
                    metrics["foundational_understanding"] = aggregates["foundational_understanding"]
                    metrics["applied_mastery"] = aggregates["applied_mastery"]
                    metrics["metacognitive_awareness"] = aggregates["metacognitive_awareness"]
                except Exception as e:
                    print(f"[Metrics] Warning: Failed to compute aggregates: {e}")

        return metrics

    def _detect_trajectory_events(self, *, prev_metrics: Optional[Dict[str, Any]], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect significant change events from previous checkpoint to current metrics."""
        events: List[Dict[str, Any]] = []
        if not prev_metrics:
            return events

        def _changed(k: str) -> bool:
            return prev_metrics.get(k) != metrics.get(k) and metrics.get(k) is not None

        # Categorical flips
        if _changed("pacing_preference"):
            events.append({"kind": "pacing_changed", "summary": f"Pacing shifted to {metrics.get('pacing_preference')}", "evidence_quote": None})
        if _changed("uncertainty_tolerance"):
            events.append({"kind": "uncertainty_changed", "summary": f"Uncertainty tolerance shifted to {metrics.get('uncertainty_tolerance')}", "evidence_quote": None})
        if _changed("curiosity_type"):
            events.append({"kind": "curiosity_changed", "summary": f"Curiosity type shifted to {metrics.get('curiosity_type')}", "evidence_quote": None})

        # Confidence jumps
        for ck in ["confidence_in_profile", "confidence_in_target"]:
            a = prev_metrics.get(ck)
            b = metrics.get(ck)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(b - a) >= 0.2:
                events.append({"kind": f"{ck}_jump", "summary": f"{ck} changed by {b - a:+.2f}", "evidence_quote": None})

        return events

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def get_or_create_user(self, user_id: str) -> UserProfile:
        """
        Get existing user or create new profile with default values.

        Args:
            user_id: Unique user identifier

        Returns:
            UserProfile object
        """
        session = self._get_session()
        try:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()

            if not user:
                user = UserProfile(
                    user_id=user_id,
                    curiosity_type={"value": None, "confidence": 0.0, "evidence": []},
                    entry_mode={"people": 0.0, "problems": 0.0, "ideas": 0.0},
                    uncertainty_tolerance={"value": None, "confidence": 0.0, "evidence": []},
                    interest_phase_default={"value": None, "confidence": 0.0, "notes": ""},
                    motivation_profile={
                        "intrinsic_value": 0.0,
                        "utility_value": 0.0,
                        "identity_value": 0.0,
                        "perceived_cost": 0.0
                    },
                    pacing_preference={"value": None, "confidence": 0.0},
                    riasec_hint={"I": 0.0, "A": 0.0, "S": 0.0, "R": 0.0, "E": 0.0, "C": 0.0},
                    communication_style={
                        "verbosity": "medium",
                        "complexity": "medium",
                        "emotional_expression": "neutral",
                        "question_asking_frequency": "medium"
                    },
                    total_sessions=0,
                    total_topics_explored=0
                )
                session.add(user)
                session.commit()
                session.refresh(user)

            return user
        finally:
            session.close()

    def update_user_profile(self, user_id: str, profile_updates: Dict[str, Any]):
        """
        Update user profile with new data.

        Args:
            user_id: User identifier
            profile_updates: Dictionary of fields to update
        """
        session = self._get_session()
        try:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                for field, value in profile_updates.items():
                    if hasattr(user, field):
                        setattr(user, field, value)
                session.commit()
        finally:
            session.close()

    def create_session(self, session_id: str, user_id: str) -> ConversationSession:
        """
        Create new conversation session.

        Args:
            session_id: Unique session identifier
            user_id: User identifier

        Returns:
            ConversationSession object
        """
        session = self._get_session()
        try:
            conv_session = ConversationSession(
                session_id=session_id,
                user_id=user_id
            )
            session.add(conv_session)

            # Increment user's total session count
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                user.total_sessions += 1

            session.commit()
            session.refresh(conv_session)
            return conv_session
        finally:
            session.close()

    def save_session_state(self, session_id: str, schema_state: Dict[str, Any]):
        """
        Save current schema state to session.

        Args:
            session_id: Session identifier
            schema_state: Complete schema state as dictionary
        """
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                conv_session.schema_state = schema_state
                conv_session.turns_elapsed = schema_state.get("interview_state", {}).get("turns_elapsed", 0)
                session.commit()
        finally:
            session.close()

    def end_session(self, session_id: str, final_topic: Optional[str] = None):
        """
        Mark session as ended.

        Args:
            session_id: Session identifier
            final_topic: Final topic if teaching phase started
        """
        from datetime import datetime

        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                conv_session.ended_at = datetime.utcnow()
                if final_topic:
                    conv_session.final_topic = final_topic
                session.commit()
        finally:
            session.close()

    def log_signal(self, user_id: str, session_id: str, signal_data: Dict[str, Any]):
        """
        Log a signal extracted during conversation.

        Args:
            user_id: User identifier
            session_id: Session identifier
            signal_data: Dictionary with turn, signal_type, evidence_quote, interpretation, updates_field, confidence
        """
        session = self._get_session()
        try:
            signal = Signal(
                user_id=user_id,
                session_id=session_id,
                **signal_data
            )
            session.add(signal)
            session.commit()
        finally:
            session.close()

    def get_user_signals(self, user_id: str, limit: Optional[int] = None):
        """
        Get all signals for a user.

        Args:
            user_id: User identifier
            limit: Optional limit on number of signals

        Returns:
            List of Signal objects
        """
        session = self._get_session()
        try:
            query = session.query(Signal).filter_by(user_id=user_id).order_by(Signal.timestamp.desc())
            if limit:
                query = query.limit(limit)
            return query.all()
        finally:
            session.close()

    def get_user_sessions(self, user_id: str):
        """
        Get all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            List of ConversationSession objects
        """
        session = self._get_session()
        try:
            return session.query(ConversationSession).filter_by(user_id=user_id).order_by(ConversationSession.started_at.desc()).all()
        finally:
            session.close()

    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get schema state for a session.

        Args:
            session_id: Session identifier

        Returns:
            Schema state dictionary or None
        """
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            return conv_session.schema_state if conv_session else None
        finally:
            session.close()

    # ============================================
    # User Login / Authentication Methods
    # ============================================

    def get_user_by_username(self, username: str) -> Optional[UserProfile]:
        """Get user by username."""
        session = self._get_session()
        try:
            return session.query(UserProfile).filter_by(username=username).first()
        finally:
            session.close()

    def create_user_with_username(self, username: str, onboarding_info: str = "") -> UserProfile:
        """Create a new user with username."""
        import uuid
        session = self._get_session()
        try:
            user = UserProfile(
                user_id=str(uuid.uuid4()),
                username=username,
                onboarding_info=onboarding_info,
                curiosity_type={"value": None, "confidence": 0.0, "evidence": []},
                entry_mode={"people": 0.0, "problems": 0.0, "ideas": 0.0},
                uncertainty_tolerance={"value": None, "confidence": 0.0, "evidence": []},
                interest_phase_default={"value": None, "confidence": 0.0, "notes": ""},
                motivation_profile={
                    "intrinsic_value": 0.0,
                    "utility_value": 0.0,
                    "identity_value": 0.0,
                    "perceived_cost": 0.0
                },
                pacing_preference={"value": None, "confidence": 0.0},
                riasec_hint={"I": 0.0, "A": 0.0, "S": 0.0, "R": 0.0, "E": 0.0, "C": 0.0},
                communication_style={
                    "verbosity": "medium",
                    "complexity": "medium",
                    "emotional_expression": "neutral",
                    "question_asking_frequency": "medium"
                },
                total_sessions=0,
                total_topics_explored=0
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
        finally:
            session.close()

    def update_user_onboarding(self, user_id: str, onboarding_info: str):
        """Update user's onboarding info."""
        session = self._get_session()
        try:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                user.onboarding_info = onboarding_info
                session.commit()
        finally:
            session.close()

    # ============================================
    # Goal Management Methods
    # ============================================

    def create_goal(self, user_id: str, goal_text: str) -> UserGoal:
        """Create a new goal for user."""
        session = self._get_session()
        try:
            goal = UserGoal(
                user_id=user_id,
                goal_text=goal_text,
                status='active'
            )
            session.add(goal)
            session.commit()
            session.refresh(goal)
            return goal
        finally:
            session.close()

    def get_user_goals(self, user_id: str) -> list:
        """Get all goals for a user."""
        session = self._get_session()
        try:
            goals = session.query(UserGoal).filter_by(user_id=user_id).order_by(UserGoal.created_at.desc()).all()
            # Convert to dicts to avoid detached instance issues
            return [
                {
                    "id": g.id,
                    "goal_text": g.goal_text,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                    "status": g.status,
                    "has_teaching_candidate": bool(g.has_teaching_candidate),
                    "teaching_candidate": g.teaching_candidate
                }
                for g in goals
            ]
        finally:
            session.close()

    def update_goal_teaching_candidate(self, goal_id: int, teaching_candidate: Dict[str, Any]):
        """Update goal with teaching candidate info (legacy single candidate)."""
        session = self._get_session()
        try:
            goal = session.query(UserGoal).filter_by(id=goal_id).first()
            if goal:
                goal.teaching_candidate = teaching_candidate
                goal.has_teaching_candidate = 1
                session.commit()
        finally:
            session.close()

    def set_goal_teaching_candidates(self, goal_id: int, teaching_candidates: list[Dict[str, Any]]):
        """Set all teaching candidates for a goal (replaces existing)."""
        session = self._get_session()
        try:
            goal = session.query(UserGoal).filter_by(id=goal_id).first()
            if goal:
                # Store as array in teaching_candidate JSON field
                goal.teaching_candidate = teaching_candidates
                goal.has_teaching_candidate = 1 if teaching_candidates else 0
                session.commit()
        finally:
            session.close()

    # ============================================
    # Exploration Session Methods
    # ============================================

    def get_user_exploration_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's active exploration session."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(
                user_id=user_id,
                session_type='exploration',
                ended_at=None
            ).order_by(ConversationSession.started_at.desc()).first()
            
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed
                }
            return None
        finally:
            session.close()

    def create_session_with_type(self, session_id: str, user_id: str, session_type: str = 'exploration', goal_id: int = None, teaching_candidate_id: int = None) -> ConversationSession:
        """Create session with type (exploration, goal, or teaching)."""
        session = self._get_session()
        try:
            conv_session = ConversationSession(
                session_id=session_id,
                user_id=user_id,
                session_type=session_type,
                goal_id=goal_id,
                teaching_candidate_id=teaching_candidate_id,
                conversation_history=[]
            )
            session.add(conv_session)

            # Increment user's total session count
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                user.total_sessions += 1

            session.commit()
            session.refresh(conv_session)
            return conv_session
        finally:
            session.close()

    def get_session_for_goal(self, goal_id: int) -> Optional[Dict[str, Any]]:
        """Get the session associated with a goal."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(
                goal_id=goal_id,
                session_type='goal'
            ).order_by(ConversationSession.started_at.desc()).first()
            
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary
                }
            return None
        finally:
            session.close()

    def get_session_for_teaching(self, goal_id: int, teaching_candidate_id: int) -> Optional[Dict[str, Any]]:
        """Get the teaching session for a specific goal and teaching candidate."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(
                goal_id=goal_id,
                teaching_candidate_id=teaching_candidate_id,
                session_type='teaching'
            ).order_by(ConversationSession.started_at.desc()).first()
            
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary,
                    "goal_id": conv_session.goal_id,
                    "teaching_candidate_id": conv_session.teaching_candidate_id
                }
            return None
        finally:
            session.close()

    def get_or_create_teaching_session(self, user_id: str, goal_id: int, teaching_candidate_id: int) -> Dict[str, Any]:
        """Get existing teaching session or create a new one."""
        session = self._get_session()
        try:
            # Look for existing active teaching session for this goal + candidate
            conv_session = session.query(ConversationSession).filter_by(
                goal_id=goal_id,
                teaching_candidate_id=teaching_candidate_id,
                session_type='teaching',
                ended_at=None
            ).order_by(ConversationSession.started_at.desc()).first()
            
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary,
                    "goal_id": conv_session.goal_id,
                    "teaching_candidate_id": conv_session.teaching_candidate_id,
                    "is_new": False
                }
            
            # Create new teaching session
            import uuid
            new_session_id = str(uuid.uuid4())
            conv_session = ConversationSession(
                session_id=new_session_id,
                user_id=user_id,
                session_type='teaching',
                goal_id=goal_id,
                teaching_candidate_id=teaching_candidate_id,
                conversation_history=[]
            )
            session.add(conv_session)
            
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                user.total_sessions += 1
            
            session.commit()
            
            return {
                "session_id": new_session_id,
                "conversation_history": [],
                "schema_state": None,
                "turns_elapsed": 0,
                "profile_summary": None,
                "goal_id": goal_id,
                "teaching_candidate_id": teaching_candidate_id,
                "is_new": True
            }
        finally:
            session.close()

    def get_goal_by_id(self, goal_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific goal by ID."""
        session = self._get_session()
        try:
            goal = session.query(UserGoal).filter_by(id=goal_id).first()
            if goal:
                return {
                    "id": goal.id,
                    "user_id": goal.user_id,
                    "goal_text": goal.goal_text,
                    "status": goal.status,
                    "teaching_candidate": goal.teaching_candidate,
                    "has_teaching_candidate": bool(goal.has_teaching_candidate)
                }
            return None
        finally:
            session.close()

    def get_or_create_exploration_session(self, user_id: str) -> Dict[str, Any]:
        """Get existing exploration session or create a new one."""
        session = self._get_session()
        try:
            # Look for existing active exploration session
            conv_session = session.query(ConversationSession).filter_by(
                user_id=user_id,
                session_type='exploration',
                ended_at=None
            ).order_by(ConversationSession.started_at.desc()).first()
            
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary,
                    "is_new": False
                }
            
            # Create new session
            import uuid
            new_session_id = str(uuid.uuid4())
            conv_session = ConversationSession(
                session_id=new_session_id,
                user_id=user_id,
                session_type='exploration',
                conversation_history=[]
            )
            session.add(conv_session)
            
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user:
                user.total_sessions += 1
            
            session.commit()
            
            return {
                "session_id": new_session_id,
                "conversation_history": [],
                "schema_state": None,
                "turns_elapsed": 0,
                "profile_summary": None,
                "is_new": True
            }
        finally:
            session.close()

    def link_session_to_goal(self, session_id: str, goal_id: int):
        """Link an existing session to a goal (when goal is created from exploration).
        
        Note: Goal sessions start FRESH - they don't copy exploration history.
        The user profile/schema is shared, but conversation is separate.
        """
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                # Create a NEW session for the goal - DO NOT copy conversation history
                # Goal conversations are separate from exploration
                import uuid
                new_session = ConversationSession(
                    session_id=str(uuid.uuid4()),
                    user_id=conv_session.user_id,
                    session_type='goal',
                    goal_id=goal_id,
                    conversation_history=[],  # Fresh start - no history copied
                    schema_state=None  # Fresh schema for goal phase
                )
                session.add(new_session)
                session.commit()
                return new_session.session_id
            return None
        finally:
            session.close()

    def save_conversation_history(self, session_id: str, conversation_history: list):
        """Save conversation history for a session."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                conv_session.conversation_history = conversation_history
                conv_session.turns_elapsed = len([m for m in conversation_history if m.get("role") == "user"])
                session.commit()
        finally:
            session.close()

    def get_conversation_history(self, session_id: str) -> list:
        """Get conversation history for a session."""
        session_data = self.get_session_by_id(session_id)
        if session_data:
            return session_data.get("conversation_history", [])
        return []

    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by its ID."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                return {
                    "session_id": conv_session.session_id,
                    "user_id": conv_session.user_id,
                    "session_type": conv_session.session_type,
                    "goal_id": conv_session.goal_id,
                    "teaching_candidate_id": conv_session.teaching_candidate_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary
                }
            return None
        finally:
            session.close()

    def list_sessions_for_goal(self, goal_id: int) -> List[Dict[str, Any]]:
        """Get all conversation sessions associated with a specific goal."""
        session = self._get_session()
        try:
            conv_sessions = session.query(ConversationSession).filter_by(goal_id=goal_id).order_by(ConversationSession.started_at.asc()).all()
            results = []
            for conv_session in conv_sessions:
                results.append({
                    "session_id": conv_session.session_id,
                    "user_id": conv_session.user_id,
                    "session_type": conv_session.session_type,
                    "goal_id": conv_session.goal_id,
                    "teaching_candidate_id": conv_session.teaching_candidate_id,
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "started_at": conv_session.started_at.isoformat() if conv_session.started_at else None,
                    "ended_at": conv_session.ended_at.isoformat() if conv_session.ended_at else None,
                    "status": conv_session.schema_state.get("status") if isinstance(conv_session.schema_state, dict) else None
                })
            return results
        finally:
            session.close()

    def list_trajectory_checkpoints_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all trajectory checkpoints for a specific session."""
        session = self._get_session()
        try:
            checkpoints = session.query(TrajectoryCheckpoint).filter_by(session_id=session_id).order_by(TrajectoryCheckpoint.turn_index.asc()).all()
            results = []
            for cp in checkpoints:
                results.append({
                    "id": cp.id,
                    "user_id": cp.user_id,
                    "session_id": cp.session_id,
                    "session_type": cp.session_type,
                    "goal_id": cp.goal_id,
                    "turn_index": cp.turn_index,
                    "metrics": cp.metrics,
                    "events": cp.events,
                    "created_at": cp.created_at.isoformat() if cp.created_at else None
                })
            return results
        finally:
            session.close()

    def save_profile_summary(self, session_id: str, summary: str):
        """Save the LLM-generated profile summary for a session."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                conv_session.profile_summary = summary
                session.commit()
        finally:
            session.close()

    # ============================================
    # Feed Item Methods
    # ============================================

    def get_feed_items(self, user_id: str, context_type: str, goal_id: int = None, 
                       teaching_candidate_id: str = None) -> List[Dict[str, Any]]:
        """Get feed items for a specific context."""
        session = self._get_session()
        try:
            query = session.query(FeedItem).filter_by(
                user_id=user_id,
                context_type=context_type
            )
            
            if context_type == 'goal' and goal_id:
                query = query.filter_by(goal_id=goal_id)
            elif context_type == 'teaching_candidate' and teaching_candidate_id:
                query = query.filter_by(teaching_candidate_id=teaching_candidate_id)
            
            items = query.order_by(FeedItem.display_order).all()
            
            return [
                {
                    "id": item.id,
                    "title": item.title,
                    "content": item.content,
                    "source_citation": item.source_citation,
                    "source_url": item.source_url,
                    "relevance_note": item.relevance_note,
                    "display_order": item.display_order,
                }
                for item in items
            ]
        finally:
            session.close()

    def save_feed_items(self, user_id: str, context_type: str, items: List[Dict[str, Any]],
                        goal_id: int = None, teaching_candidate_id: str = None):
        """Save multiple feed items for a context."""
        session = self._get_session()
        try:
            for i, item_data in enumerate(items):
                feed_item = FeedItem(
                    user_id=user_id,
                    context_type=context_type,
                    goal_id=goal_id,
                    teaching_candidate_id=teaching_candidate_id,
                    title=item_data.get("title", ""),
                    content=item_data.get("content", ""),
                    source_citation=item_data.get("source_citation"),
                    source_url=item_data.get("source_url"),
                    relevance_note=item_data.get("relevance_note"),
                    display_order=i
                )
                session.add(feed_item)
            session.commit()
        finally:
            session.close()

    def has_feed_items(self, user_id: str, context_type: str, goal_id: int = None,
                       teaching_candidate_id: str = None) -> bool:
        """Check if feed items exist for a context."""
        session = self._get_session()
        try:
            query = session.query(FeedItem).filter_by(
                user_id=user_id,
                context_type=context_type
            )
            
            if context_type == 'goal' and goal_id:
                query = query.filter_by(goal_id=goal_id)
            elif context_type == 'teaching_candidate' and teaching_candidate_id:
                query = query.filter_by(teaching_candidate_id=teaching_candidate_id)
            
            return query.first() is not None
        finally:
            session.close()
