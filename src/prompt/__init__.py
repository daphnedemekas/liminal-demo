"""Prompt component system for structured context assembly."""
from src.prompt.components import (
    PromptComponents,
    ClipboardContent,
    Voice,
)
from src.prompt.gather import (
    gather_docs,
    gather_conversation,
    gather_schema,
    gather_teaching_context,
    gather_prompt_components,
)
from src.prompt.formatter import (
    format_prompt,
    format_files,
)
from src.prompt.assembly import (
    assemble_prompt,
)

__all__ = [
    "PromptComponents",
    "ClipboardContent",
    "Voice",
    "gather_docs",
    "gather_conversation",
    "gather_schema",
    "gather_teaching_context",
    "gather_prompt_components",
    "format_prompt",
    "format_files",
    "assemble_prompt",
]

