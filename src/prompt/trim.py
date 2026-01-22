"""Priority-based trimming of prompt components to fit token budget."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from src.prompt.components import PromptComponents
from src.prompt.tokens import count_tokens, MAX_SAFE_TOKENS


@dataclass(frozen=True)
class DroppedComponent:
    """Component dropped to fit token limits."""
    
    kind: str
    name: Optional[str] = None
    tokens: int = 0
    reason: Optional[str] = None


@dataclass
class _DropCandidate:
    """Internal candidate for dropping."""
    
    kind: str
    name: Optional[str]
    tokens: int
    path: Optional[Path] = None
    priority: int = 0  # Lower priority = dropped first


def _total_component_tokens(components: PromptComponents) -> int:
    """Calculate total tokens across all components."""
    total = 0
    
    # System instructions (never dropped, but count tokens)
    if components.system_instructions:
        total += count_tokens(components.system_instructions)
    
    # Step/task (never dropped, but count tokens)
    if components.step:
        _, content = components.step
        total += count_tokens(content)
    
    # Documentation
    if components.docs:
        total += sum(count_tokens(content) for _path, content in components.docs)
    
    # Diff
    if components.diff:
        total += count_tokens(components.diff)
    
    # Diff files
    if components.diff_files:
        total += sum(count_tokens(content) for _path, content in components.diff_files)
    
    # Summaries
    if components.summaries:
        total += sum(count_tokens(content) for _path, content in components.summaries)
    
    # Clipboard
    if components.clipboard and components.clipboard.text:
        total += count_tokens(components.clipboard.text)
    
    # Voices
    if components.voices:
        total += sum(count_tokens(v.content) for v in components.voices)
    
    # Liminal-specific: Conversation history
    if components.conversation_history:
        from src.prompt.gather import gather_conversation
        conv_text = gather_conversation(components.conversation_history)
        if conv_text:
            total += count_tokens(conv_text)
    
    # Liminal-specific: Schema state
    if components.schema_state:
        import json
        schema_json = json.dumps(components.schema_state)
        total += count_tokens(schema_json)
    
    # Liminal-specific: User background
    if components.user_background:
        total += count_tokens(components.user_background)
    
    # Liminal-specific: Goal context
    if components.goal_context:
        import json
        goal_json = json.dumps(components.goal_context)
        total += count_tokens(goal_json)
    
    return total


def _drop_candidates(components: PromptComponents) -> List[_DropCandidate]:
    """
    Generate list of candidates that can be dropped, with priority.
    
    Priority order (lower = dropped first):
    1. diff_files, summaries (lowest priority)
    2. docs, old conversation_history (medium priority)
    3. diff, clipboard, recent conversation (higher priority)
    4. step, system_instructions (never dropped - not included)
    """
    candidates: List[_DropCandidate] = []
    
    # Lowest priority: diff_files (entire section)
    if components.diff_files:
        diff_files_tokens = sum(count_tokens(content) for _path, content in components.diff_files)
        if diff_files_tokens > 0:
            candidates.append(_DropCandidate("diff_files", None, diff_files_tokens, priority=1))
    
    # Lowest priority: summaries
    if components.summaries:
        for summary_path, content in components.summaries:
            tokens = count_tokens(content)
            if tokens > 0:
                candidates.append(_DropCandidate("summaries", str(summary_path), tokens, path=summary_path, priority=1))
    
    # Medium priority: docs
    if components.docs:
        for doc_path, content in components.docs:
            tokens = count_tokens(content)
            if tokens > 0:
                candidates.append(_DropCandidate("docs", doc_path.name, tokens, path=doc_path, priority=2))
    
    # Medium priority: old conversation history (trim from beginning)
    if components.conversation_history and len(components.conversation_history) > 6:
        # Drop oldest messages (keep last 6)
        old_messages = components.conversation_history[:-6]
        from src.prompt.gather import gather_conversation
        old_conv_text = gather_conversation(old_messages)
        if old_conv_text:
            tokens = count_tokens(old_conv_text)
            if tokens > 0:
                candidates.append(_DropCandidate("conversation_old", "old_messages", tokens, priority=2))
    
    # Higher priority: diff
    if components.diff:
        tokens = count_tokens(components.diff)
        if tokens > 0:
            candidates.append(_DropCandidate("diff", "branch diff", tokens, priority=3))
    
    # Higher priority: clipboard
    if components.clipboard and components.clipboard.text:
        tokens = count_tokens(components.clipboard.text)
        if tokens > 0:
            candidates.append(_DropCandidate("clipboard", "pasted text", tokens, priority=3))
    
    return candidates


def _apply_drop_candidate(components: PromptComponents, candidate: _DropCandidate) -> None:
    """Apply a drop candidate to the components."""
    if candidate.kind == "diff_files":
        components.diff_files = []
    elif candidate.kind == "summaries":
        if components.summaries:
            components.summaries = [
                (path, content)
                for path, content in components.summaries
                if path != candidate.path
            ]
    elif candidate.kind == "docs":
        if components.docs:
            components.docs = [
                (path, content)
                for path, content in components.docs
                if path != candidate.path
            ]
    elif candidate.kind == "conversation_old":
        # Keep only last 6 messages
        if components.conversation_history and len(components.conversation_history) > 6:
            components.conversation_history = components.conversation_history[-6:]
    elif candidate.kind == "diff":
        components.diff = None
    elif candidate.kind == "clipboard":
        components.clipboard = None


def trim_prompt_components(
    components: PromptComponents,
    max_tokens: int = MAX_SAFE_TOKENS
) -> Tuple[PromptComponents, List[DroppedComponent]]:
    """
    Trim prompt components to fit token budget using priority-based dropping.
    
    Priority order (dropped first to last):
    1. diff_files, summaries (lowest priority)
    2. docs, old conversation_history (medium priority)
    3. diff, clipboard, recent conversation (higher priority)
    4. step/task prompt, system_instructions (never dropped - highest priority)
    
    Args:
        components: PromptComponents to trim
        max_tokens: Maximum token budget (default: MAX_SAFE_TOKENS)
        
    Returns:
        Tuple of (trimmed PromptComponents, list of DroppedComponent objects)
    """
    dropped: List[DroppedComponent] = []
    total_tokens = _total_component_tokens(components)
    
    # If already under budget, return as-is
    if total_tokens <= max_tokens:
        return components, dropped
    
    # Special case: if diff_files alone exceeds limit, drop it entirely
    if components.diff_files:
        diff_files_tokens = sum(count_tokens(content) for _path, content in components.diff_files)
        if diff_files_tokens > max_tokens:
            components.diff_files = []
            dropped.append(
                DroppedComponent("diff_files", None, diff_files_tokens, reason="exceeds limit")
            )
            total_tokens = _total_component_tokens(components)
            if total_tokens <= max_tokens:
                return components, dropped
    
    # Greedy trimming: drop largest lowest-priority components first
    while total_tokens > max_tokens:
        candidates = _drop_candidates(components)
        if not candidates:
            break
        
        # Sort by priority (ascending), then by tokens (descending)
        candidates.sort(key=lambda c: (c.priority, -c.tokens))
        candidate = candidates[0]
        
        if candidate.tokens <= 0:
            break
        
        _apply_drop_candidate(components, candidate)
        dropped.append(
            DroppedComponent(
                candidate.kind,
                candidate.name,
                candidate.tokens,
                reason="greedy"
            )
        )
        total_tokens = _total_component_tokens(components)
    
    # Last resort: drop all diff_files if still over budget
    if total_tokens > max_tokens and components.diff_files:
        diff_files_tokens = sum(count_tokens(content) for _path, content in components.diff_files)
        components.diff_files = []
        dropped.append(
            DroppedComponent("diff_files", None, diff_files_tokens, reason="last resort")
        )
    
    return components, dropped

