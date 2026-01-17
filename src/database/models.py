"""SQLAlchemy models for persistent storage."""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class UserProfile(Base):
    """Persistent user profile across sessions."""

    __tablename__ = 'user_profiles'

    user_id = Column(String, primary_key=True)  # UUID or cookie ID
    username = Column(String, unique=True, nullable=True, index=True)  # For login
    onboarding_info = Column(Text, nullable=True)  # User's background info
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Aggregate profile data (JSON)
    # Each field stores: {value, confidence, evidence[], notes}
    curiosity_type = Column(JSON)  # {value: "interest"/"deprivation"/"mixed", confidence, evidence[]}
    entry_mode = Column(JSON)      # {people: 0.0-1.0, problems: 0.0-1.0, ideas: 0.0-1.0}
    uncertainty_tolerance = Column(JSON)  # {value: "low"/"medium"/"high", confidence, evidence[]}
    interest_phase_default = Column(JSON)  # {value: "triggered"/"maintained"/"emerging"/"developed", confidence, notes}
    motivation_profile = Column(JSON)  # {intrinsic_value: 0.0-1.0, utility_value: 0.0-1.0, identity_value: 0.0-1.0, perceived_cost: 0.0-1.0}
    pacing_preference = Column(JSON)  # {value: "fast_resolution"/"exploratory"/"mixed", confidence}
    riasec_hint = Column(JSON)  # {I: 0.0-1.0, A: 0.0-1.0, S: 0.0-1.0, R: 0.0-1.0, E: 0.0-1.0, C: 0.0-1.0}

    # Communication style tracking
    communication_style = Column(JSON)  # {verbosity, complexity, emotional_expression, question_asking_frequency}

    # Meta information
    total_sessions = Column(Integer, default=0)
    total_topics_explored = Column(Integer, default=0)

    # Relationships
    sessions = relationship("ConversationSession", back_populates="user", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("UserGoal", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UserProfile(user_id='{self.user_id}', sessions={self.total_sessions})>"


class ConversationSession(Base):
    """Individual conversation session."""

    __tablename__ = 'conversation_sessions'

    session_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    # Session type: 'exploration' or 'goal'
    session_type = Column(String, default='exploration')
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=True)

    # Session state (JSON)
    schema_state = Column(JSON)  # Full JSON schema snapshot at end
    conversation_history = Column(JSON, default=list)  # List of messages [{role, content}]
    final_topic = Column(String, nullable=True)
    final_topic_id = Column(Integer, nullable=True)
    teaching_started = Column(Integer, default=0)  # Boolean as int

    # Session metrics
    turns_elapsed = Column(Integer, default=0)
    topics_mentioned = Column(Integer, default=0)
    topics_fully_probed = Column(Integer, default=0)
    
    # Profile summary (LLM-generated)
    profile_summary = Column(String, nullable=True)

    # Relationships
    user = relationship("UserProfile", back_populates="sessions")
    goal = relationship("UserGoal", back_populates="sessions")

    def __repr__(self):
        return f"<ConversationSession(session_id='{self.session_id}', user_id='{self.user_id}', turns={self.turns_elapsed})>"


class UserGoal(Base):
    """User's accepted learning goals."""

    __tablename__ = 'user_goals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    goal_text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Status: 'active', 'completed', 'archived'
    status = Column(String, default='active')
    
    # Teaching candidate info (when found)
    teaching_candidate = Column(JSON, nullable=True)
    has_teaching_candidate = Column(Integer, default=0)  # Boolean as int
    
    # Relationships
    user = relationship("UserProfile", back_populates="goals")
    sessions = relationship("ConversationSession", back_populates="goal")

    def __repr__(self):
        return f"<UserGoal(id={self.id}, goal='{self.goal_text[:30]}...', status='{self.status}')>"


class Signal(Base):
    """Individual signals extracted during conversation."""

    __tablename__ = 'signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    session_id = Column(String, ForeignKey('conversation_sessions.session_id'))
    turn = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Signal content
    signal_type = Column(String)  # affect, value, goal, confusion, preference, identity, etc.
    evidence_quote = Column(Text)  # Direct quote from user message
    interpretation = Column(Text)  # What this signal means
    updates_field = Column(String)  # e.g., "user_profile.curiosity_type"
    confidence = Column(Float)  # 0.0-1.0

    # Relationships
    user = relationship("UserProfile", back_populates="signals")

    def __repr__(self):
        return f"<Signal(id={self.id}, type='{self.signal_type}', confidence={self.confidence})>"


class FeedItem(Base):
    """Feed content items for learning context."""

    __tablename__ = 'feed_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Context type: 'exploration', 'goal', or 'teaching_candidate'
    context_type = Column(String, nullable=False)
    
    # Reference IDs (null for exploration, goal_id for goal context, etc.)
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=True)
    teaching_candidate_id = Column(String, nullable=True)  # From schema, not a FK
    
    # Content
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)  # Short paragraph
    source_citation = Column(String, nullable=True)  # Academic reference
    source_url = Column(String, nullable=True)  # Link if available
    relevance_note = Column(String, nullable=True)  # Why this is relevant
    
    # Ordering
    display_order = Column(Integer, default=0)

    def __repr__(self):
        return f"<FeedItem(id={self.id}, type='{self.context_type}', title='{self.title[:30]}...')>"
