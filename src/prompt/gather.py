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
    )

