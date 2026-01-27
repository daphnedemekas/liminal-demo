"""Prompt component data structures for structured context assembly."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union


@dataclass
class ClipboardContent:
    """Content from clipboard - text, image, or both."""

    text: Optional[str] = None
    image_path: Optional[Path] = None


@dataclass
class Voice:
    """Voice/persona definition for prompt styling."""

    name: str
    content: str


@dataclass
class PromptComponents:
    """
    Raw components of a prompt before assembly.
    
    This dataclass holds all context pieces needed to build a prompt,
    following LoopFlow's architecture pattern. It separates context gathering
    from formatting, making the system easier to maintain and ensuring no
    relevant context is forgotten.
    
    Liminal-specific fields (conversation_history, schema_state, user_background,
    goal_context) are added to support the discovery and teaching conversation flows.
    """

    # Required fields (must come first)
    repo_root: Path  # Required: repository root path
    
    # Core LoopFlow fields (with defaults)
    run_mode: Optional[str] = None  # "auto" or "interactive"
    docs: List[Tuple[Path, str]] = field(default_factory=list)  # Documentation files (path, content)
    diff: Optional[str] = None  # Git diff summary
    diff_files: List[Tuple[Path, str]] = field(default_factory=list)  # Full content of changed files
    step: Optional[Tuple[str, str]] = None  # (step_name, step_content) for the task
    clipboard: Optional[ClipboardContent] = None  # Text or images from clipboard
    system_instructions: Optional[str] = None  # System-level instructions (like loopflow_doc)
    voices: List[Voice] = field(default_factory=list)  # Persona definitions to include
    image_files: List[Path] = field(default_factory=list)  # Any images to embed in prompt
    summaries: List[Tuple[str, str]] = field(default_factory=list)  # Pre-generated summaries of code
    
    # Liminal-specific additions
    conversation_history: Optional[List[Dict[str, str]]] = None  # Chat conversation history
    schema_state: Optional[Dict[str, Any]] = None  # Serialized schema state
    user_background: Optional[str] = None  # User background information
    goal_context: Optional[Dict[str, Any]] = None  # Goal-specific context

    # Panel context (Context, Draft, Terminal tabs)
    goal_context_items: List[Dict[str, Any]] = field(default_factory=list)  # Context tab items
    active_document: Optional[Dict[str, Any]] = None  # Draft tab document
    terminal_observation: Optional[Dict[str, Any]] = None  # Terminal activity observation

    # Channel-specific context for suggestions
    channel_suggestion_context: Optional[Dict[str, Any]] = None  # User's instructions for suggestions

