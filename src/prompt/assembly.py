"""Central prompt assembly helper that encapsulates the full workflow."""
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from src.prompt.components import PromptComponents
from src.prompt.gather import (
    gather_prompt_components,
    gather_schema,
    gather_teaching_context,
)
from src.prompt.formatter import format_prompt
from src.prompt.trim import trim_prompt_components, DroppedComponent, MAX_SAFE_TOKENS
from src.prompt_loader import PromptLoader


def assemble_prompt(
    step_name: str,
    prompt_loader: PromptLoader,
    repo_root: Path,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    schema_state: Optional[Any] = None,
    user_background: Optional[str] = None,
    goal_context: Optional[Dict[str, Any]] = None,
    teaching_context: Optional[Dict[str, Any]] = None,
    system_instructions: Optional[str] = None,
    max_tokens: int = MAX_SAFE_TOKENS,
    variant: Optional[str] = None,
    phase: Optional[str] = None,
    task: Optional[str] = None,  # "ranker", "interviewer", "teaching"
    inject_resources: bool = True,
) -> Tuple[str, List[DroppedComponent]]:
    """
    Assemble a prompt using the full LoopFlow workflow.
    
    This function:
    1. Loads prompt template from PromptLoader
    2. Gathers context into PromptComponents
    3. Formats with XML tags
    4. Trims to token budget
    5. Returns formatted prompt and dropped components
    
    Args:
        step_name: Name of the step/prompt to load
        prompt_loader: PromptLoader instance
        repo_root: Repository root path
        conversation_history: Optional conversation history
        schema_state: Optional schema state object
        user_background: Optional user background information
        goal_context: Optional goal-specific context
        teaching_context: Optional teaching-specific context
        system_instructions: Optional system-level instructions
        max_tokens: Maximum token budget (default: MAX_SAFE_TOKENS)
        variant: Optional variant for ranker prompts (e.g., "goal_discovery", "teaching_discovery")
        phase: Optional phase for interviewer prompts (e.g., "goal_discovery", "teaching_discovery")
        task: Task type - "ranker", "interviewer", or "teaching" (default: "ranker")
        inject_resources: Whether to inject background resources (default: True)
        
    Returns:
        Tuple of (formatted_prompt_string, list_of_dropped_components)
    """
    # Step 1: Load prompt template
    if task == "teaching":
        # Load from prompts/teaching/ directory
        prompt_path = prompt_loader.prompts_dir / "teaching" / f"{step_name}.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Teaching prompt not found: {prompt_path}")
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        
        # Inject resources if needed
        if inject_resources:
            prompt_template = prompt_loader.resources.inject(prompt_template)
            
    elif task == "interviewer":
        # Use PromptLoader's interviewer prompt loading
        prompt_template = prompt_loader.load_interviewer_prompt(
            branch_condition=step_name,
            phase=phase,
            inject_resources=inject_resources
        )
    else:
        # Default: ranker prompt
        variant_str = variant or "shared"
        prompt_template = prompt_loader.load_ranker_prompt(
            task=step_name,
            variant=variant_str,
            inject_resources=inject_resources
        )
    
    # Step 2: Gather context into PromptComponents
    # Merge teaching_context into goal_context if both provided
    merged_goal_context = goal_context or {}
    if teaching_context:
        merged_goal_context = {**merged_goal_context, **teaching_context}
    
    components = gather_prompt_components(
        repo_root=repo_root,
        step=(step_name, prompt_template),
        conversation_history=conversation_history,
        schema_state=schema_state,
        user_background=user_background,
        goal_context=merged_goal_context if merged_goal_context else None,
        system_instructions=system_instructions,
    )
    
    # Step 3: Format with XML tags
    formatted = format_prompt(components)
    
    # Step 4: Trim to token budget
    trimmed_components, dropped = trim_prompt_components(components, max_tokens=max_tokens)
    
    # Step 5: Format trimmed components
    final_prompt = format_prompt(trimmed_components)
    
    # Log dropped components if any
    if dropped:
        dropped_summary = ", ".join([f"{d.kind}({d.tokens} tokens)" for d in dropped])
        print(f"[PromptAssembly] Dropped components for {step_name}: {dropped_summary}")
    
    return final_prompt, dropped

