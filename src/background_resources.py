"""
Background resources injection for prompts.
Replaces [CONCEPT_NAME] with definitions from background_resources.txt
"""
import re
from pathlib import Path
from typing import List, Optional, Dict


class BackgroundResources:
    """Loads and injects research concept definitions into prompts."""

    def __init__(self, resources_path: Optional[Path] = None):
        """
        Initialize the background resources loader.

        Args:
            resources_path: Path to background_resources.txt.
                          If None, uses prompts/background_resources.txt
        """
        if resources_path is None:
            # Default to prompts/background_resources.txt relative to project root
            project_root = Path(__file__).parent.parent
            resources_path = project_root / "prompts" / "background_resources.txt"

        self.resources_path = resources_path
        self.resources: Dict[str, str] = {}
        self._load_resources()

    def _load_resources(self):
        """Load resources from background_resources.txt"""
        if not self.resources_path.exists():
            raise FileNotFoundError(
                f"Background resources file not found: {self.resources_path}"
            )

        with open(self.resources_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse [CONCEPT]: definition format
        # Pattern matches [CONCEPT_NAME]: followed by definition until next [CONCEPT] or end
        pattern = r'\[([A-Z_]+)\]:\s*(.+?)(?=\n\n\[|\n\[|$)'
        matches = re.findall(pattern, content, re.DOTALL)

        for concept, definition in matches:
            # Clean up the definition: remove extra whitespace, normalize
            definition = ' '.join(definition.split())
            self.resources[concept] = definition.strip()

    def inject(self, prompt: str, concepts: Optional[List[str]] = None) -> str:
        """
        Inject resource definitions into prompt.

        If concepts is None, auto-detect [CONCEPT_NAME] references.
        Otherwise, inject only specified concepts.

        Args:
            prompt: The prompt text with [CONCEPT_NAME] placeholders
            concepts: Optional list of concept names to inject. If None, auto-detects.

        Returns:
            Prompt with [CONCEPT_NAME] replaced by definitions

        Example:
            >>> resources = BackgroundResources()
            >>> prompt = "Use [FRICTION_PROBE] to identify the gap."
            >>> resources.inject(prompt)
            "Use 'Where does your understanding stop feeling crisp?' - Identifies knowledge edge... to identify the gap."
        """
        if concepts is None:
            # Auto-detect referenced concepts
            concepts = re.findall(r'\[([A-Z_]+)\]', prompt)

        # Inject definitions
        for concept in set(concepts):
            if concept in self.resources:
                # Replace [CONCEPT] with actual definition
                prompt = prompt.replace(
                    f'[{concept}]',
                    self.resources[concept]
                )
            else:
                # Leave undefined concepts as-is (could also raise warning)
                pass

        return prompt

    def get_definition(self, concept: str) -> str:
        """
        Get definition for a single concept.

        Args:
            concept: The concept name (without brackets)

        Returns:
            Definition string, or error message if undefined
        """
        return self.resources.get(concept, f"[Undefined concept: {concept}]")

    def list_concepts(self) -> List[str]:
        """
        Get list of all available concept names.

        Returns:
            List of concept names
        """
        return sorted(self.resources.keys())

    def reload(self):
        """Reload resources from file (useful if file was updated)."""
        self.resources.clear()
        self._load_resources()


if __name__ == "__main__":
    # Test the resource injection system
    resources = BackgroundResources()

    print("Available concepts:")
    for concept in resources.list_concepts()[:5]:
        print(f"  - {concept}")
    print(f"  ... and {len(resources.list_concepts()) - 5} more\n")

    # Test injection
    test_prompt = """
    You are using [I_TYPE_CURIOSITY] and [D_TYPE_CURIOSITY] to understand the user.

    Use [FRICTION_PROBE] to identify gaps.
    """

    print("Original prompt:")
    print(test_prompt)
    print("\nAfter injection:")
    print(resources.inject(test_prompt))
