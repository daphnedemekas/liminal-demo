"""Session manager for handling conversation state."""
import sys
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.agents.orchestrator import DiscoveryOrchestrator


class FinalTopic:
    """Simplified final topic representation for backend compatibility."""
    def __init__(self, topic: str, user_confusion: str = "", stakes: str = "", learning_hook: str = "", suggested_angles: list = None, scores: dict = None):
        self.topic = topic
        self.user_confusion = user_confusion
        self.stakes = stakes
        self.learning_hook = learning_hook
        self.suggested_angles = suggested_angles or []
        self.scores = scores or {}


class SessionData:
    """Data stored for each session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.discovery_session: Optional[DiscoveryOrchestrator] = None
        self.final_topic: Optional[FinalTopic] = None
        self.learning_conversation: list = []
        self.learning_state: str = "not_started"  # not_started, assess, identify, explain, complete
        self.created_at: datetime = datetime.now()
        self.last_activity: datetime = datetime.now()


class SessionManager:
    """Manages active conversation sessions."""

    def __init__(self):
        self.sessions: Dict[str, SessionData] = {}

    def create_session(
        self, 
        session_id: str, 
        debug: bool = False, 
        model_config: Optional[Dict] = None, 
        user_goal: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_history: Optional[list] = None,
        schema_state: Optional[dict] = None
    ) -> SessionData:
        """Initialize new discovery session or resume existing one."""
        session_data = SessionData(session_id)
        
        # Pass all parameters to orchestrator
        session_data.discovery_session = DiscoveryOrchestrator(
            user_id=user_id or session_id,
            model_config=model_config,
            user_goal=user_goal,
            session_id=session_id,  # Always pass session_id - database ID is source of truth
            conversation_history=conversation_history,
            schema_state=schema_state
        )
        
        # Store goal in schema if provided (for new sessions without restored state)
        if user_goal and not schema_state:
            session_data.discovery_session.schema.interview_state.user_goal = user_goal
            session_data.discovery_session.schema.interview_state.goal_provided = True
            session_data.discovery_session.schema.interview_state.goal_identified = True  # Goal upfront = already identified
            print(f"[SessionManager] User goal set: {user_goal}")

        self.sessions[session_id] = session_data
        return session_data

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Retrieve existing session."""
        session_data = self.sessions.get(session_id)
        if session_data:
            session_data.last_activity = datetime.now()
        return session_data

    def save_final_topic(self, session_id: str, topic: FinalTopic):
        """Store discovered topic for learning phase."""
        session_data = self.get_session(session_id)
        if session_data:
            session_data.final_topic = topic
            session_data.learning_state = "ready"

    def delete_session(self, session_id: str):
        """Remove session from memory."""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove sessions older than max_age_hours."""
        now = datetime.now()
        to_delete = []
        for session_id, session_data in self.sessions.items():
            age = (now - session_data.last_activity).total_seconds() / 3600
            if age > max_age_hours:
                to_delete.append(session_id)

        for session_id in to_delete:
            self.delete_session(session_id)


# Global session manager instance
session_manager = SessionManager()
