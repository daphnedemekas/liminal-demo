"""Database manager for user profiles and sessions."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
from typing import Optional, Dict, Any, List
import json

from .models import Base, UserProfile, ConversationSession, Signal, UserGoal, FeedItem


class DatabaseManager:
    """Manages database operations for user profiles, sessions, and signals."""

    def __init__(self, db_path: str = "data/liminal.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

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
        """Update goal with teaching candidate info."""
        session = self._get_session()
        try:
            goal = session.query(UserGoal).filter_by(id=goal_id).first()
            if goal:
                goal.teaching_candidate = teaching_candidate
                goal.has_teaching_candidate = 1
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

    def save_conversation_history(self, session_id: str, conversation_history: list):
        """Save conversation history to session."""
        session = self._get_session()
        try:
            conv_session = session.query(ConversationSession).filter_by(session_id=session_id).first()
            if conv_session:
                conv_session.conversation_history = conversation_history
                session.commit()
        finally:
            session.close()

    def create_session_with_type(self, session_id: str, user_id: str, session_type: str = 'exploration', goal_id: int = None) -> ConversationSession:
        """Create session with type (exploration or goal)."""
        session = self._get_session()
        try:
            conv_session = ConversationSession(
                session_id=session_id,
                user_id=user_id,
                session_type=session_type,
                goal_id=goal_id,
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
                    "conversation_history": conv_session.conversation_history or [],
                    "schema_state": conv_session.schema_state,
                    "turns_elapsed": conv_session.turns_elapsed,
                    "profile_summary": conv_session.profile_summary
                }
            return None
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
                    "display_order": item.display_order
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
