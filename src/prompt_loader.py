"""Modular prompt loading system."""
from pathlib import Path
from typing import Optional, List
from src.background_resources import BackgroundResources


class PromptLoader:
    """Dynamically loads prompts based on branch conditions and injects resources."""

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Path to prompts directory. If None, uses project_root/prompts
        """
        if prompts_dir is None:
            project_root = Path(__file__).parent.parent
            prompts_dir = project_root / "prompts"

        self.prompts_dir = prompts_dir
        self.resources = BackgroundResources()
        self._prompt_cache = {}

    def load_interviewer_prompt(
        self,
        branch_condition: str,
        phase: Optional[str] = None,
        inject_resources: bool = True
    ) -> str:
        """
        Load interviewer prompt based on branch condition and phase.

        Args:
            branch_condition: Prompt module to load. Can be:
                - conversation_mode: calibration, grounded_offer, hypothesis_correct, direct_probe
                - opening (for initial questions)
                - general_continuation (fallback for any unmatched condition)
            phase: Discovery phase for phase-specific prompts:
                - "goal_discovery" - Phase 1 (finding learning goal)
                - "teaching_discovery" - Phase 2 (finding teaching target)
                - None - use shared prompts only
            inject_resources: Whether to inject background resource definitions

        Returns:
            Complete prompt with base + conditional module
        """
        # Load base prompt
        base_path = self.prompts_dir / "interviewer" / "base.txt"
        if not base_path.exists():
            raise FileNotFoundError(f"Base interviewer prompt not found: {base_path}")

        with open(base_path, 'r', encoding='utf-8') as f:
            base_prompt = f.read()

        # Load conditional module - try phase-specific first, then shared
        conditional_prompt = ""
        
        # Phase-specific prompts (calibration, grounded_offer, hypothesis_correct, direct_probe)
        if phase:
            phase_path = self.prompts_dir / "interviewer" / phase / f"{branch_condition}.txt"
            if phase_path.exists():
                with open(phase_path, 'r', encoding='utf-8') as f:
                    conditional_prompt = f.read()
        
        # Fall back to shared prompts (opening, general_continuation)
        if not conditional_prompt:
            shared_path = self.prompts_dir / "interviewer" / f"{branch_condition}.txt"
            if shared_path.exists():
                with open(shared_path, 'r', encoding='utf-8') as f:
                    conditional_prompt = f.read()
            else:
                # Final fallback to general_continuation
                fallback_path = self.prompts_dir / "interviewer" / "general_continuation.txt"
                if fallback_path.exists():
                    with open(fallback_path, 'r', encoding='utf-8') as f:
                        conditional_prompt = f.read()

        # Build bridge section
        phase_label = "Goal Discovery" if phase == "goal_discovery" else "Teaching Discovery" if phase == "teaching_discovery" else "Discovery"
        mode_label = branch_condition.replace("_", " ").title()
        
        bridge = f"""
=== CURRENT TURN GUIDANCE ===

PHASE: {phase_label}
CONVERSATION MODE: {mode_label}

The following is specific guidance for this conversation mode. Use it alongside the principles above, but trust your judgment — if the conversation calls for something different, follow the flow.

"""

        # Combine: base + bridge + mode-specific
        full_prompt = f"{base_prompt}\n{bridge}{conditional_prompt}"

        # Inject background resources if needed
        if inject_resources:
            full_prompt = self.resources.inject(full_prompt)

        return full_prompt

    def load_ranker_prompt(self, task: str, inject_resources: bool = True, variant: str = "shared") -> str:
        """
        Load ranker prompt for specific task.

        Args:
            task: One of:
                - update_user_profile
                - update_conversational_themes_delta
                - update_goal_candidates (goal_discovery only)
                - update_teaching_candidates (teaching_discovery only)
                - generate_controller
            inject_resources: Whether to inject background resource definitions
            variant: Subdirectory to load from:
                - "shared" - common prompts for all rankers (default)
                - "goal_discovery" - prompts for Phase 1 (finding learning goal)
                - "teaching_discovery" - prompts for Phase 2 (finding teaching target)

        Returns:
            Prompt for that ranker task
        """
        # Try variant-specific path first
        variant_path = self.prompts_dir / "ranker" / variant / f"{task}.txt"

        # Fall back to root ranker directory for backward compatibility
        fallback_path = self.prompts_dir / "ranker" / f"{task}.txt"

        # Determine which path to use
        if variant_path.exists():
            path = variant_path
        elif fallback_path.exists():
            path = fallback_path
        else:
            raise FileNotFoundError(
                f"Ranker prompt not found. Tried:\n"
                f"  - {variant_path}\n"
                f"  - {fallback_path}"
            )

        with open(path, 'r', encoding='utf-8') as f:
            prompt = f.read()

        if inject_resources:
            prompt = self.resources.inject(prompt)

        return prompt

    def get_opening_questions(self) -> List[str]:
        """
        Load opening question bank.

        Returns:
            List of opening questions
        """
        path = self.prompts_dir / "interviewer" / "opening.txt"
        if not path.exists():
            # Return default questions if file doesn't exist
            return [
                "What have you been curious about lately?",
                "Is there anything you've been wanting to understand better?",
                "What's something you've been wondering about recently?"
            ]

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse questions - only extract lines marked with "## Q:"
        questions = []
        for line in content.split('\n'):
            line = line.strip()
            # Only extract lines that start with "## Q:" marker
            if line.startswith('## Q:'):
                # Remove the "## Q:" prefix and any leading/trailing whitespace
                question = line[5:].strip()
                if question:
                    questions.append(question)

        # If no questions found with markers, return sensible defaults
        if not questions:
            return [
                "When you're curious about something, does it usually feel like you're filling in a gap in something you already care about, or exploring completely new territory?",
                "When you want to understand something, which pull is usually stronger - how it works, or what it means?",
                "Is your curiosity more like a spotlight on one thing, or more like a floodlight across many things?"
            ]

        return questions

    def reload_resources(self):
        """Reload background resources (useful if file was updated)."""
        self.resources.reload()
        self._prompt_cache.clear()
