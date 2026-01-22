"""Flow execution engine for multi-step agent workflows."""
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from src.flows.flow import FlowDef, FlowStep, Choose, Join
from src.llm_client import LLMClient
from src.prompt.components import PromptComponents
from src.prompt.gather import gather_prompt_components
from src.prompt.formatter import format_prompt
from src.prompt.trim import trim_prompt_components, MAX_SAFE_TOKENS


class FlowContext:
    """Context passed between flow steps."""
    
    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        self.data = initial_data or {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from context."""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in context."""
        self.data[key] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update context with dictionary."""
        self.data.update(updates)


class FlowExecutor:
    """
    Executes flow definitions with support for:
    - Sequential execution
    - Fork/join with parallel LLM calls
    - Choose branches (LLM-driven decision)
    - Context passing between steps
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        repo_root: Path,
        step_executor: Optional[Callable[[str, Dict[str, Any], FlowContext], Any]] = None
    ):
        """
        Initialize flow executor.
        
        Args:
            llm_client: LLM client for making API calls
            repo_root: Repository root path
            step_executor: Optional custom function to execute steps.
                         If None, uses default LLM-based execution.
                         Signature: (step_name: str, config: dict, context: FlowContext) -> result
        """
        self.llm = llm_client
        self.repo_root = repo_root
        self.step_executor = step_executor or self._default_step_executor
    
    def execute(
        self,
        flow: FlowDef,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> FlowContext:
        """
        Execute a flow definition.
        
        Args:
            flow: FlowDef to execute
            initial_context: Optional initial context data
            
        Returns:
            FlowContext with final state after execution
        """
        context = FlowContext(initial_context)
        
        # Resolve flow steps (expand nested flows)
        resolved_steps = self._resolve_flow(flow)
        
        i = 0
        while i < len(resolved_steps):
            step = resolved_steps[i]
            
            if step.fork is not None:
                # Fork: execute steps in parallel, then join
                join_step = None
                if i + 1 < len(resolved_steps) and resolved_steps[i + 1].join is not None:
                    join_step = resolved_steps[i + 1]
                
                result = self._execute_fork_join(step.fork, join_step, context)
                if result is not None:
                    context.update(result)
                
                # Skip join step (already processed)
                if join_step:
                    i += 2
                else:
                    i += 1
                    
            elif step.choose is not None:
                # Choose: LLM decides which branch to take
                choice = self._execute_choose(step.choose, context)
                branch_steps = step.choose.options.get(choice, [])
                
                if branch_steps:
                    # Replace choose step with chosen branch
                    branch_flow = FlowDef(
                        name=f"{flow.name}:{choice}",
                        steps=[FlowStep.from_dict(s) if isinstance(s, dict) else FlowStep(step=s) for s in branch_steps]
                    )
                    branch_resolved = self._resolve_flow(branch_flow)
                    resolved_steps = resolved_steps[:i] + branch_resolved + resolved_steps[i + 1:]
                    # Don't increment i - process the new branch steps
                    continue
                else:
                    i += 1
                    
            elif step.flow is not None:
                # Nested flow: recursively execute
                # For now, treat as step name (would need flow loading)
                result = self.step_executor(step.flow, step.config.model_dump(exclude_none=True) if step.config else {}, context)
                if result:
                    context.update(result)
                i += 1
                
            elif step.step is not None:
                # Sequential step
                config = step.config.model_dump(exclude_none=True) if step.config else {}
                result = self.step_executor(step.step, config, context)
                if result:
                    context.update(result)
                i += 1
            else:
                i += 1
        
        return context
    
    def _resolve_flow(self, flow: FlowDef) -> List[FlowStep]:
        """
        Resolve flow steps, expanding nested flows.
        
        For now, returns steps as-is. In the future, could load nested flows.
        """
        return flow.steps
    
    def _execute_fork_join(
        self,
        fork_steps: List[FlowStep],
        join_step: Optional[FlowStep],
        context: FlowContext
    ) -> Optional[Dict[str, Any]]:
        """
        Execute fork steps in parallel, then join results.
        
        Args:
            fork_steps: List of steps to execute in parallel
            join_step: Optional join step to merge results
            context: Current flow context
            
        Returns:
            Merged results from join step, or None
        """
        # Execute all fork steps in parallel
        with ThreadPoolExecutor(max_workers=len(fork_steps)) as executor:
            futures = {}
            for step in fork_steps:
                config = step.config.model_dump(exclude_none=True) if step.config else {}
                if step.step:
                    future = executor.submit(self.step_executor, step.step, config, context)
                    futures[future] = step.step or "unknown"
            
            # Collect results
            results = {}
            for future in as_completed(futures):
                step_name = futures[future]
                try:
                    result = future.result()
                    results[step_name] = result
                except Exception as e:
                    print(f"[FlowExecutor] Fork step {step_name} failed: {e}")
                    results[step_name] = {"error": str(e)}
        
        # If join step exists, merge results
        if join_step and join_step.join:
            return self._execute_join(join_step.join, results, context)
        
        # Otherwise, merge all results into context
        merged = {}
        for step_name, result in results.items():
            if isinstance(result, dict):
                merged.update(result)
            else:
                merged[step_name] = result
        
        return merged
    
    def _execute_join(
        self,
        join: Join,
        fork_results: Dict[str, Any],
        context: FlowContext
    ) -> Dict[str, Any]:
        """
        Execute join step to merge fork results.
        
        Args:
            join: Join configuration
            fork_results: Results from fork steps
            context: Current flow context
            
        Returns:
            Merged results (includes fork_results)
        """
        merged = fork_results.copy()
        
        if join.join.step:
            # Execute join step with fork results as context
            join_context = FlowContext({**context.data, "fork_results": fork_results})
            config = {}
            if join.join.agent_model:
                config["model"] = join.join.agent_model
            
            result = self.step_executor(join.join.step, config, join_context)
            if result:
                # Merge join result with fork results
                merged.update(result)
        
        return merged
    
    def _execute_choose(
        self,
        choose: Choose,
        context: FlowContext
    ) -> str:
        """
        Execute choose step: LLM decides which branch to take.
        
        Args:
            choose: Choose configuration
            context: Current flow context
            
        Returns:
            Selected branch name
        """
        # Build prompt for choice
        options_list = list(choose.options.keys())
        prompt_text = choose.prompt or f"Choose one of the following options: {', '.join(options_list)}"
        
        # Add context to prompt
        if context.data:
            context_json = json.dumps(context.data, indent=2)
            prompt_text = f"{prompt_text}\n\nCurrent context:\n{context_json}"
        
        prompt_text = f"{prompt_text}\n\nRespond with ONLY the option name: {', '.join(options_list)}"
        
        # Call LLM
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt_text}],
            model="gpt-4o",
            temperature=0.3,
            max_tokens=50
        )
        
        # Parse choice from response
        choice = response.strip().lower()
        for option in options_list:
            if option.lower() in choice or choice in option.lower():
                return option
        
        # Default to first option if parsing fails
        print(f"[FlowExecutor] Warning: Could not parse choice from '{response}', defaulting to first option")
        return options_list[0]
    
    def _default_step_executor(
        self,
        step_name: str,
        config: Dict[str, Any],
        context: FlowContext
    ) -> Dict[str, Any]:
        """
        Default step executor using LLM.
        
        This is a placeholder - in practice, steps would load prompts
        and execute them with the LLM, then return results.
        
        Args:
            step_name: Name of step to execute
            config: Step configuration
            context: Current flow context
            
        Returns:
            Step execution result
        """
        # For now, return context updates
        # In full implementation, would:
        # 1. Load prompt for step_name
        # 2. Gather prompt components with context
        # 3. Format and trim prompt
        # 4. Call LLM
        # 5. Parse and return result
        
        return {"step_executed": step_name, "context": context.data}

