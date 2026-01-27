"""Pydantic models for Panel Context (Context, Draft, Terminal tabs)."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from datetime import datetime


# ============================================================================
# Enums for Panel Context
# ============================================================================

class ContentType(str, Enum):
    """Type of context content."""
    TEXT = "text"
    FILE = "file"
    IMAGE = "image"
    CODE = "code"


class DocumentType(str, Enum):
    """Type of document."""
    ESSAY = "essay"
    APPLICATION = "application"
    CODE = "code"
    NOTES = "notes"


class ChannelType(str, Enum):
    """Type of chat channel."""
    MAIN = "main"
    SANDBOX = "sandbox"
    DRAFT = "draft"
    CUSTOM = "custom"


class MessageType(str, Enum):
    """Type of channel message."""
    CHAT = "chat"
    SUGGESTION = "suggestion"
    OBSERVATION = "observation"
    TASK_PROPOSAL = "task_proposal"


class MessageSource(str, Enum):
    """Source of a message."""
    TERMINAL_OBSERVATION = "terminal_observation"
    DOCUMENT_ANALYSIS = "document_analysis"
    USER_INPUT = "user_input"


class SourceBinding(str, Enum):
    """Source binding for chat channels."""
    TERMINAL = "terminal"
    DOCUMENT = "document"
    BOTH = "both"


# ============================================================================
# Context Tab Models
# ============================================================================

class GoalContextItem(BaseModel):
    """Individual context item for a goal."""
    id: int
    goal_id: int
    user_id: str
    content_type: ContentType = ContentType.TEXT

    # Text content
    text_content: Optional[str] = None

    # File content
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_mime_type: Optional[str] = None

    # Processed content for LLM
    processed_content: Optional[str] = None

    # Token tracking
    token_count: int = 0

    # Status
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ContextUploadRequest(BaseModel):
    """Request to upload a context file."""
    goal_id: int
    user_id: str
    file_name: str
    file_mime_type: str


class ContextTextRequest(BaseModel):
    """Request to add text context."""
    goal_id: int
    user_id: str
    text_content: str
    content_type: ContentType = ContentType.TEXT


# ============================================================================
# Draft Tab Models
# ============================================================================

class SuggestionConfig(BaseModel):
    """Configuration for AI suggestions on documents."""
    formatting: bool = True
    content: bool = True
    tasks: bool = False
    custom_instructions: Optional[str] = None


class GoalDocumentInfo(BaseModel):
    """Document information for a goal."""
    id: int
    goal_id: int
    user_id: str
    title: str = "Untitled"
    document_type: DocumentType = DocumentType.NOTES

    # Content
    content: Optional[Dict[str, Any]] = None  # Rich text JSON
    plain_text: Optional[str] = None

    # Configuration
    suggestion_config: SuggestionConfig = Field(default_factory=SuggestionConfig)

    # Metadata
    token_count: int = 0
    version: int = 1
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentCreateRequest(BaseModel):
    """Request to create a new document."""
    goal_id: int
    user_id: str
    title: str = "Untitled"
    document_type: DocumentType = DocumentType.NOTES
    content: Optional[Dict[str, Any]] = None
    plain_text: Optional[str] = None


class DocumentUpdateRequest(BaseModel):
    """Request to update a document."""
    title: Optional[str] = None
    document_type: Optional[DocumentType] = None
    content: Optional[Dict[str, Any]] = None
    plain_text: Optional[str] = None


class DocumentSuggestion(BaseModel):
    """AI suggestion for a document."""
    suggestion_type: Literal["formatting", "content", "task", "general"]
    text: str
    location: Optional[str] = None  # Where in document this applies
    confidence: float = 0.8


# ============================================================================
# Terminal Tab Models
# ============================================================================

class CommandEntry(BaseModel):
    """A single command entry in terminal history."""
    command: str
    output: str
    exit_code: int = 0
    timestamp: str


class TerminalSessionInfo(BaseModel):
    """Terminal session information."""
    id: int
    session_id: str
    goal_id: int
    user_id: str
    working_directory: str = "~"
    environment_vars: Dict[str, str] = Field(default_factory=dict)
    command_history: List[CommandEntry] = Field(default_factory=list)
    observation_buffer: List[CommandEntry] = Field(default_factory=list)
    is_active: bool = True
    created_at: Optional[str] = None
    ended_at: Optional[str] = None


class TerminalStartRequest(BaseModel):
    """Request to start a terminal session."""
    goal_id: int
    user_id: str
    working_directory: str = "~"
    environment_vars: Dict[str, str] = Field(default_factory=dict)


class TerminalInputMessage(BaseModel):
    """WebSocket message for terminal input."""
    type: Literal["input"] = "input"
    data: str


class TerminalResizeMessage(BaseModel):
    """WebSocket message for terminal resize."""
    type: Literal["resize"] = "resize"
    rows: int
    cols: int


class TerminalOutputMessage(BaseModel):
    """WebSocket message for terminal output."""
    type: Literal["output"] = "output"
    data: str


class TerminalObservationMessage(BaseModel):
    """WebSocket message for AI observation."""
    type: Literal["observation"] = "observation"
    activity: str
    suggestion: Optional[str] = None


# ============================================================================
# Chat Channel Models
# ============================================================================

class SuggestionContext(BaseModel):
    """Context for AI suggestions in a channel."""
    instructions: Optional[str] = None
    focus_areas: List[str] = Field(default_factory=list)
    excluded_topics: List[str] = Field(default_factory=list)


class ChatChannelInfo(BaseModel):
    """Chat channel information."""
    id: int
    goal_id: int
    user_id: str
    channel_type: ChannelType = ChannelType.MAIN
    name: str
    suggestion_context: SuggestionContext = Field(default_factory=SuggestionContext)
    source_binding: Optional[SourceBinding] = None
    is_active: bool = True
    created_at: Optional[str] = None


class ChannelCreateRequest(BaseModel):
    """Request to create a new chat channel."""
    goal_id: int
    user_id: str
    channel_type: ChannelType = ChannelType.CUSTOM
    name: str
    suggestion_context: Optional[SuggestionContext] = None
    source_binding: Optional[SourceBinding] = None


class ChannelMessageInfo(BaseModel):
    """Channel message information."""
    id: int
    channel_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: MessageType = MessageType.CHAT
    source: Optional[MessageSource] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ChannelMessageRequest(BaseModel):
    """Request to send a message to a channel."""
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: MessageType = MessageType.CHAT
    source: Optional[MessageSource] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# WebSocket Message Protocols
# ============================================================================

class DocumentWSUpdateMessage(BaseModel):
    """WebSocket: Client sends document update."""
    type: Literal["update"] = "update"
    content: Dict[str, Any]
    plain_text: str


class DocumentWSRequestSuggestion(BaseModel):
    """WebSocket: Client requests suggestion."""
    type: Literal["request_suggestion"] = "request_suggestion"
    selection: Optional[str] = None


class DocumentWSUpdateConfig(BaseModel):
    """WebSocket: Client updates suggestion config."""
    type: Literal["update_config"] = "update_config"
    config: SuggestionConfig


class DocumentWSSuggestionsResponse(BaseModel):
    """WebSocket: Server sends suggestions."""
    type: Literal["suggestions"] = "suggestions"
    suggestions: List[DocumentSuggestion]


class DocumentWSSyncAck(BaseModel):
    """WebSocket: Server acknowledges sync."""
    type: Literal["sync_ack"] = "sync_ack"
    version: int


class ChannelWSMessage(BaseModel):
    """WebSocket: Message in a channel."""
    type: Literal["message"] = "message"
    message: ChannelMessageInfo


class ChannelWSSuggestion(BaseModel):
    """WebSocket: AI suggestion in a channel."""
    type: Literal["suggestion"] = "suggestion"
    content: str
    source: MessageSource
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Prompt Context Aggregation
# ============================================================================

class PanelContextForPrompt(BaseModel):
    """Aggregated panel context for prompt assembly."""

    # Context tab items (processed for LLM)
    goal_context_items: List[Dict[str, Any]] = Field(default_factory=list)
    total_context_tokens: int = 0

    # Active document (if any)
    active_document: Optional[Dict[str, Any]] = None
    document_tokens: int = 0

    # Terminal observation (rolling window)
    terminal_observation: Optional[Dict[str, Any]] = None
    terminal_tokens: int = 0

    # Channel context (for suggestion generation)
    channel_suggestion_context: Optional[SuggestionContext] = None

    class Config:
        """Pydantic config."""
        extra = "allow"


class ObservationSummary(BaseModel):
    """Summary of terminal/document activity for AI."""
    activity_type: Literal["terminal", "document", "both"]
    summary: str
    recent_commands: Optional[List[str]] = None
    detected_patterns: List[str] = Field(default_factory=list)
    suggested_topics: List[str] = Field(default_factory=list)
