"""Pydantic models for API requests and responses."""
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    """Request to create a new discovery session."""
    models: Optional[Dict[str, str]] = None  # e.g., {"interviewer": "cerebras:llama-3.3-70b", "ranker": "anthropic:claude-sonnet-4-20250514"}
    goal: Optional[str] = None  # User's optional learning goal
    user_id: Optional[str] = None  # User ID for persistence
    goal_id: Optional[int] = None  # Goal ID to resume existing goal session


class SessionCreateResponse(BaseModel):
    """Response when creating a new session."""
    session_id: str
    opening_message: str
    audio_url: Optional[str] = None
    conversation_history: List[dict] = []  # For resuming sessions
    is_resumed: bool = False
    profile_summary: Optional[str] = None  # LLM-generated profile summary


class MessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    is_audio: bool = False


class MessageResponse(BaseModel):
    """Response containing assistant's message."""
    content: str
    audio_url: Optional[str] = None
    type: Literal["message", "topic_found"] = "message"
    topic: Optional[dict] = None


class TopicFoundResponse(BaseModel):
    """Response when a topic has been identified."""
    topic: str
    user_confusion: str
    stakes: str
    learning_hook: str
    suggested_angles: List[str]
    scores: dict


class LearningStartRequest(BaseModel):
    """Request to start the learning phase."""
    session_id: str


class LearningStartResponse(BaseModel):
    """Response when starting learning phase."""
    opening_message: str
    audio_url: Optional[str] = None
    state: Literal["assess", "identify", "explain"]
