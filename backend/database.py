"""Database setup and SQLAlchemy models."""

import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, JSON, ForeignKey,
    create_engine, event
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ── Models ──────────────────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=new_uuid)
    name = Column(String, nullable=False)
    user_type = Column(String, default="exploring")  # business|developer|student|researcher|individual|exploring
    onboarding_info = Column(Text, default="")
    onboarding_complete = Column(Boolean, default=False)
    default_involvement = Column(String, default="check_ins")  # hands_off|check_ins|involved
    explanation_preference = Column(String, default="brief_summary")  # just_results|brief_summary|show_your_work
    known_domains = Column(MutableDict.as_mutable(JSON), default=dict)
    connected_sources = Column(MutableList.as_mutable(JSON), default=list)
    model_summary = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    onboarding_state = relationship("OnboardingState", back_populates="user", uselist=False, cascade="all, delete-orphan")


class OnboardingState(Base):
    __tablename__ = "onboarding_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), unique=True, nullable=False)
    phase = Column(String, default="quick_context")  # quick_context|deeper_qa|exploring|complete
    gathered_signals = Column(MutableDict.as_mutable(JSON), default=dict)
    pending_questions = Column(MutableList.as_mutable(JSON), default=list)
    suggested_projects = Column(MutableList.as_mutable(JSON), default=list)
    conversation_history = Column(MutableList.as_mutable(JSON), default=list)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("UserProfile", back_populates="onboarding_state")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active")  # active|completed|archived
    involvement_level = Column(String, nullable=True)  # inherits from user if null
    budget_limit_cents = Column(Integer, nullable=True)
    budget_spent_cents = Column(Integer, default=0)
    conversation_signals = Column(MutableDict.as_mutable(JSON), default=dict)
    suggested_by_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("UserProfile", back_populates="projects")
    runs = relationship("AgentRun", back_populates="project", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="project", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="project", cascade="all, delete-orphan",
                                 order_by="ChatMessage.created_at")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False, index=True, default=new_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False, index=True)
    goal = Column(Text, nullable=False)
    status = Column(String, default="planning")  # planning|working|waiting_for_user|done|failed
    plan = Column(MutableList.as_mutable(JSON), default=list)
    current_step = Column(Integer, default=0)
    result_summary = Column(Text, default="")
    cost_cents = Column(Integer, default=0)
    token_usage = Column(MutableDict.as_mutable(JSON), default=dict)
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    enriched_instruction = Column(Text, nullable=True)
    system_prompt_hash = Column(String, nullable=True)

    project = relationship("Project", back_populates="runs")
    events = relationship("RunEvent", back_populates="run", cascade="all, delete-orphan",
                         order_by="RunEvent.sequence")


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("agent_runs.run_id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)  # action|result|source_found|file_changed|question_for_user|error
    payload = Column(MutableDict.as_mutable(JSON), nullable=False, default=dict)
    source_url = Column(String, nullable=True)
    source_title = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    run = relationship("AgentRun", back_populates="events")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user|assistant|system
    content = Column(Text, nullable=False)
    actions = Column(MutableList.as_mutable(JSON), default=list)  # [{label, action_text}]
    run_id = Column(String, ForeignKey("agent_runs.run_id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="chat_messages")


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("agent_runs.run_id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    artifact_type = Column(String, nullable=False)  # report|comparison_table|file|draft|list|spreadsheet
    title = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    sources = Column(MutableList.as_mutable(JSON), default=list)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="artifacts")


# ── Database setup ──────────────────────────────────────────────────

DB_PATH = os.environ.get("DATABASE_PATH", "data/liminal.db")

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    return _engine


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


def get_db():
    """FastAPI dependency that yields a DB session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
