"""SQLAlchemy models for persistent storage."""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, ForeignKey, Boolean
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

    # Session type: 'exploration', 'goal', or 'teaching'
    session_type = Column(String, default='exploration')
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=True)
    teaching_candidate_id = Column(Integer, nullable=True)  # ID of teaching candidate for teaching sessions

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
    contexts = relationship("GoalContext", back_populates="goal", cascade="all, delete-orphan")
    documents = relationship("GoalDocument", back_populates="goal", cascade="all, delete-orphan")
    terminal_sessions = relationship("TerminalSession", back_populates="goal", cascade="all, delete-orphan")
    chat_channels = relationship("ChatChannel", back_populates="goal", cascade="all, delete-orphan")

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


class LearnerTrajectory(Base):
    """Canonical longitudinal learner dashboard state (one row per user)."""

    __tablename__ = "learner_trajectories"

    user_id = Column(String, ForeignKey("user_profiles.user_id"), primary_key=True)
    dashboard_state = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checkpoint_id = Column(Integer, nullable=True)

    user = relationship("UserProfile")

    def __repr__(self):
        return f"<LearnerTrajectory(user_id='{self.user_id}', last_checkpoint_id={self.last_checkpoint_id})>"


class TrajectoryCheckpoint(Base):
    """Sparse, append-only checkpoints for trajectory computation/plotting."""

    __tablename__ = "trajectory_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.user_id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session_id = Column(String, ForeignKey("conversation_sessions.session_id"), nullable=True, index=True)
    session_type = Column(String, nullable=True)  # exploration | goal | teaching
    goal_id = Column(Integer, ForeignKey("user_goals.id"), nullable=True, index=True)
    teaching_candidate_id = Column(Integer, nullable=True, index=True)
    turn_index = Column(Integer, nullable=True)

    metrics = Column(JSON, nullable=False, default=dict)
    events = Column(JSON, nullable=False, default=list)
    source_summary = Column(Text, nullable=True)

    user = relationship("UserProfile")
    session = relationship("ConversationSession")
    goal = relationship("UserGoal")

    def __repr__(self):
        return f"<TrajectoryCheckpoint(id={self.id}, user_id='{self.user_id}', session_type='{self.session_type}')>"


class GoalContext(Base):
    """User-provided context materials for a learning goal."""

    __tablename__ = 'goal_contexts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Content type: 'text', 'file', 'image', 'code'
    content_type = Column(String, nullable=False, default='text')

    # For pasted text content
    text_content = Column(Text, nullable=True)

    # For file uploads
    file_path = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_mime_type = Column(String, nullable=True)

    # Processed content for LLM (OCR results, parsed code, etc.)
    processed_content = Column(Text, nullable=True)

    # Token count for budget management
    token_count = Column(Integer, default=0)

    # Soft delete flag
    is_active = Column(Boolean, default=True)

    # Relationships
    goal = relationship("UserGoal", back_populates="contexts")

    def __repr__(self):
        return f"<GoalContext(id={self.id}, goal_id={self.goal_id}, type='{self.content_type}')>"


class GoalDocument(Base):
    """User drafts associated with a learning goal."""

    __tablename__ = 'goal_documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Document metadata
    title = Column(String, default='Untitled')

    # Document type: 'essay', 'application', 'code', 'notes'
    document_type = Column(String, default='notes')

    # Content storage
    content = Column(JSON, nullable=True)  # Rich text format (JSON)
    plain_text = Column(Text, nullable=True)  # Plain text for LLM processing

    # Suggestion configuration
    # {"formatting": true, "content": true, "tasks": false}
    suggestion_config = Column(JSON, default=dict)

    # Token count for budget management
    token_count = Column(Integer, default=0)

    # Version tracking
    version = Column(Integer, default=1)

    # Soft delete flag
    is_active = Column(Boolean, default=True)

    # Relationships
    goal = relationship("UserGoal", back_populates="documents")

    def __repr__(self):
        return f"<GoalDocument(id={self.id}, goal_id={self.goal_id}, title='{self.title}')>"


class TerminalSession(Base):
    """Terminal session state for a learning goal."""

    __tablename__ = 'terminal_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False, index=True)  # UUID for WebSocket
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    # Terminal state
    working_directory = Column(String, default='~')
    environment_vars = Column(JSON, default=dict)

    # Command history: [{command, output, timestamp, exit_code}]
    command_history = Column(JSON, default=list)

    # Rolling window for AI observation
    observation_buffer = Column(JSON, default=list)

    # Session active flag
    is_active = Column(Boolean, default=True)

    # Relationships
    goal = relationship("UserGoal", back_populates="terminal_sessions")

    def __repr__(self):
        return f"<TerminalSession(id={self.id}, session_id='{self.session_id}', goal_id={self.goal_id})>"


class ChatChannel(Base):
    """Tabbed chat channel within a learning goal."""

    __tablename__ = 'chat_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey('user_goals.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Channel type: 'main', 'sandbox', 'draft', 'custom'
    channel_type = Column(String, nullable=False, default='main')

    # User-visible name ("Main Chat", "Sandbox Suggestions", etc.)
    name = Column(String, nullable=False)

    # User's instructions for what suggestions they want in this channel
    suggestion_context = Column(JSON, default=dict)

    # Which panel feeds this channel: 'terminal', 'document', 'both', null
    source_binding = Column(String, nullable=True)

    # Channel active flag
    is_active = Column(Boolean, default=True)

    # Relationships
    goal = relationship("UserGoal", back_populates="chat_channels")
    messages = relationship("ChannelMessage", back_populates="channel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatChannel(id={self.id}, goal_id={self.goal_id}, name='{self.name}')>"


class ChannelMessage(Base):
    """Messages within a chat channel."""

    __tablename__ = 'channel_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey('chat_channels.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Message role: 'user', 'assistant', 'system'
    role = Column(String, nullable=False)

    # Message content
    content = Column(Text, nullable=False)

    # Message type: 'chat', 'suggestion', 'observation', 'task_proposal'
    message_type = Column(String, default='chat')

    # What triggered this message: 'terminal_observation', 'document_analysis', 'user_input'
    source = Column(String, nullable=True)

    # Additional metadata (e.g., which command triggered this)
    message_metadata = Column(JSON, default=dict)

    # Relationships
    channel = relationship("ChatChannel", back_populates="messages")

    def __repr__(self):
        return f"<ChannelMessage(id={self.id}, channel_id={self.channel_id}, role='{self.role}')>"
