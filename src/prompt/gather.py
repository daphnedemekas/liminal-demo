"""Context gathering functions for assembling prompt components."""
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from src.prompt.components import PromptComponents, ClipboardContent, Voice


def gather_docs(repo_root: Path, exclude: Optional[List[str]] = None) -> List[Tuple[Path, str]]:
    """
    Gather documentation files from repository root.
    
    Looks for common documentation files like README.md, STYLE.md, etc.
    
    Args:
        repo_root: Repository root path
        exclude: Optional list of patterns to exclude
        
    Returns:
        List of (path, content) tuples for documentation files
    """
    docs = []
    doc_files = ["README.md", "STYLE.md", "CONTRIBUTING.md", "LICENSE"]
    
    for doc_file in doc_files:
        doc_path = repo_root / doc_file
        if doc_path.exists() and doc_path.is_file():
            try:
                content = doc_path.read_text(encoding='utf-8')
                docs.append((doc_path, content))
            except Exception as e:
                print(f"[Gather] Warning: Could not read {doc_path}: {e}")
    
    return docs


def gather_conversation(
    conversation_history: Optional[List[Dict[str, str]]],
    max_messages: int = 12,
    max_chars: int = 8000
) -> Optional[str]:
    """
    Format conversation history as readable text.
    
    Matches the format used in RankerAgentBase._format_conversation().
    Default trim to keep prompts fast and bounded as the conversation grows.
    
    Args:
        conversation_history: List of message dictionaries with 'role' and 'content'
        max_messages: Maximum number of messages to include (takes last N)
        max_chars: Maximum characters to include
        
    Returns:
        Formatted conversation string, or None if no history
    """
    if not conversation_history:
        return None
    
    # Take last N messages
    window = conversation_history[-max_messages:] if len(conversation_history) > max_messages else conversation_history
    
    lines: List[str] = []
    for msg in window:
        role = msg.get('role', 'unknown').capitalize()
        content = msg.get('content', '')
        lines.append(f"{role}: {content}")
    
    # Enforce a rough character limit by dropping oldest lines first
    while lines and sum(len(l) + 1 for l in lines) > max_chars:
        lines.pop(0)
    
    return "\n".join(lines) if lines else None


def gather_schema(schema: Any) -> Optional[Dict[str, Any]]:
    """
    Serialize schema state to dictionary.
    
    Args:
        schema: Schema object (should have model_dump() method if Pydantic)
        
    Returns:
        Serialized schema as dictionary, or None if schema is None
    """
    if schema is None:
        return None
    
    # If it's a Pydantic model, use model_dump()
    if hasattr(schema, 'model_dump'):
        return schema.model_dump()
    
    # If it's already a dict, return as-is
    if isinstance(schema, dict):
        return schema
    
    # Otherwise try to convert to dict
    try:
        return dict(schema)
    except Exception as e:
        print(f"[Gather] Warning: Could not serialize schema: {e}")
        return None


def gather_teaching_context(
    teaching_candidate: Optional[Any] = None,
    curriculum_plan: Optional[Any] = None,
    assessment_concepts_known: Optional[List[str]] = None,
    assessment_concepts_unclear: Optional[List[str]] = None,
    assessment_confidence: Optional[float] = None
) -> Dict[str, Any]:
    """
    Gather teaching-specific context.
    
    Args:
        teaching_candidate: Teaching candidate object
        curriculum_plan: Curriculum plan object
        assessment_concepts_known: List of known concepts
        assessment_concepts_unclear: List of unclear concepts
        assessment_confidence: Confidence level in assessment
        
    Returns:
        Dictionary with teaching context
    """
    context = {}
    
    if teaching_candidate:
        if hasattr(teaching_candidate, 'model_dump'):
            context['teaching_candidate'] = teaching_candidate.model_dump()
        elif isinstance(teaching_candidate, dict):
            context['teaching_candidate'] = teaching_candidate
        else:
            context['teaching_candidate'] = str(teaching_candidate)
    
    if curriculum_plan:
        if hasattr(curriculum_plan, 'model_dump'):
            context['curriculum_plan'] = curriculum_plan.model_dump()
        elif isinstance(curriculum_plan, dict):
            context['curriculum_plan'] = curriculum_plan
        else:
            context['curriculum_plan'] = str(curriculum_plan)
    
    if assessment_concepts_known:
        context['assessment_concepts_known'] = assessment_concepts_known
    
    if assessment_concepts_unclear:
        context['assessment_concepts_unclear'] = assessment_concepts_unclear
    
    if assessment_confidence is not None:
        context['assessment_confidence'] = assessment_confidence
    
    return context


def gather_goal_context_items(
    db,
    goal_id: int,
    max_tokens: int = 4000
) -> List[Dict[str, Any]]:
    """
    Gather context items from the Context tab for a goal.

    Args:
        db: DatabaseManager instance
        goal_id: ID of the goal
        max_tokens: Maximum token budget for context items

    Returns:
        List of context items, prioritized by recency and trimmed to token budget
    """
    contexts = db.get_goal_contexts(goal_id, include_inactive=False)

    if not contexts:
        return []

    # Sort by created_at (most recent first)
    contexts.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    # Collect items until we hit the token budget
    result = []
    total_tokens = 0

    for ctx in contexts:
        token_count = ctx.get("token_count", 0)
        if token_count == 0:
            # Estimate tokens from content
            content = ctx.get("processed_content") or ctx.get("text_content") or ""
            token_count = len(content.split()) * 1.3  # Rough estimate

        if total_tokens + token_count > max_tokens:
            break

        # Format for prompt
        item = {
            "id": ctx.get("id"),
            "type": ctx.get("content_type"),
            "content": ctx.get("processed_content") or ctx.get("text_content") or "",
            "file_name": ctx.get("file_name"),
        }
        result.append(item)
        total_tokens += token_count

    return result


def gather_document_context(
    document: Dict[str, Any],
    max_tokens: int = 2000
) -> Dict[str, Any]:
    """
    Gather context from the active document in Draft tab.

    Args:
        document: Document dictionary from database
        max_tokens: Maximum token budget for document content

    Returns:
        Processed document context for prompt
    """
    if not document:
        return None

    plain_text = document.get("plain_text") or ""

    # Estimate tokens and trim if needed
    estimated_tokens = len(plain_text.split()) * 1.3
    if estimated_tokens > max_tokens:
        # Trim to approximate token count
        words = plain_text.split()
        max_words = int(max_tokens / 1.3)
        plain_text = " ".join(words[:max_words]) + "..."

    return {
        "id": document.get("id"),
        "title": document.get("title", "Untitled"),
        "document_type": document.get("document_type", "notes"),
        "content": plain_text,
        "version": document.get("version", 1),
        "suggestion_config": document.get("suggestion_config", {}),
    }


def gather_terminal_observation(
    session: Dict[str, Any],
    max_commands: int = 10
) -> Dict[str, Any]:
    """
    Gather terminal observation context for prompt.

    Args:
        session: Terminal session dictionary from database
        max_commands: Maximum number of commands to include

    Returns:
        Processed terminal observation for prompt
    """
    if not session:
        return None

    observation_buffer = session.get("observation_buffer") or []

    # Take last N commands
    recent = observation_buffer[-max_commands:] if len(observation_buffer) > max_commands else observation_buffer

    if not recent:
        return {
            "has_activity": False,
            "commands": [],
            "working_directory": session.get("working_directory", "~"),
        }

    return {
        "has_activity": True,
        "commands": [
            {
                "command": cmd.get("command", ""),
                "output": cmd.get("output", "")[:500],  # Truncate long outputs
                "exit_code": cmd.get("exit_code", 0),
                "timestamp": cmd.get("timestamp"),
            }
            for cmd in recent
        ],
        "working_directory": session.get("working_directory", "~"),
    }


def gather_prompt_components(
    repo_root: Path,
    step: Optional[Tuple[str, str]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    schema_state: Optional[Any] = None,
    user_background: Optional[str] = None,
    goal_context: Optional[Dict[str, Any]] = None,
    teaching_context: Optional[Dict[str, Any]] = None,
    system_instructions: Optional[str] = None,
    run_mode: Optional[str] = None,
    exclude: Optional[List[str]] = None,
    # Panel context parameters
    goal_context_items: Optional[List[Dict[str, Any]]] = None,
    active_document: Optional[Dict[str, Any]] = None,
    terminal_observation: Optional[Dict[str, Any]] = None,
    channel_suggestion_context: Optional[Dict[str, Any]] = None,
) -> PromptComponents:
    """
    Gather all prompt components into a PromptComponents object.

    This is the main orchestrator function that collects all context pieces
    needed to build a prompt, following LoopFlow's architecture pattern.

    Args:
        repo_root: Repository root path (required)
        step: Optional (step_name, step_content) tuple for the task
        conversation_history: Optional conversation history
        schema_state: Optional schema state object
        user_background: Optional user background information
        goal_context: Optional goal-specific context
        teaching_context: Optional teaching-specific context
        system_instructions: Optional system-level instructions
        run_mode: Optional run mode ("auto" or "interactive")
        exclude: Optional list of patterns to exclude from docs
        goal_context_items: Optional list of context items from Context tab
        active_document: Optional active document from Draft tab
        terminal_observation: Optional terminal observation from Terminal tab
        channel_suggestion_context: Optional channel-specific suggestion context

    Returns:
        PromptComponents object with all gathered context
    """
    # Gather documentation
    docs = gather_docs(repo_root, exclude=exclude)
    
    # Format conversation history
    conversation_text = gather_conversation(conversation_history)
    
    # Serialize schema state
    schema_dict = gather_schema(schema_state)
    
    # Merge teaching context into goal_context if provided
    if teaching_context and goal_context:
        goal_context = {**goal_context, **teaching_context}
    elif teaching_context:
        goal_context = teaching_context
    
    return PromptComponents(
        repo_root=repo_root,
        run_mode=run_mode,
        docs=docs,
        step=step,
        system_instructions=system_instructions,
        conversation_history=conversation_history,  # Keep raw history for formatter
        schema_state=schema_dict,
        user_background=user_background,
        goal_context=goal_context,
        # Panel context
        goal_context_items=goal_context_items or [],
        active_document=active_document,
        terminal_observation=terminal_observation,
        channel_suggestion_context=channel_suggestion_context,
    )

