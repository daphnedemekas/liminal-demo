"""AI suggestions for documents."""
import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, field

# Add parent directory to path to import from src
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.llm_client import LLMClient
from src.config import get_model_name


@dataclass
class DocumentSuggestion:
    """A single suggestion for a document."""
    suggestion_type: str  # "formatting", "content", "task", "general"
    text: str
    location: Optional[str] = None
    confidence: float = 0.8
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SuggestionConfig:
    """Configuration for what suggestions to generate."""
    formatting: bool = True
    content: bool = True
    tasks: bool = False
    custom_instructions: Optional[str] = None


class DocumentSuggestionService:
    """Service for generating AI suggestions on documents."""

    def __init__(self, debounce_seconds: float = 2.0):
        self.debounce_seconds = debounce_seconds
        self._pending_documents: Dict[int, asyncio.Task] = {}
        self._last_content: Dict[int, str] = {}

    async def _debounced_generate(
        self,
        document_id: int,
        plain_text: str,
        goal_context: Dict[str, Any],
        config: SuggestionConfig,
        callback: callable
    ):
        """Generate suggestions after debounce period."""
        await asyncio.sleep(self.debounce_seconds)

        # Check if content changed during debounce
        if self._last_content.get(document_id) != plain_text:
            return

        suggestions = await self.generate_suggestions(
            document_id=document_id,
            plain_text=plain_text,
            goal_context=goal_context,
            config=config
        )

        if callback:
            await callback(suggestions)

    def schedule_suggestions(
        self,
        document_id: int,
        plain_text: str,
        goal_context: Dict[str, Any],
        config: SuggestionConfig,
        callback: callable
    ):
        """Schedule suggestion generation with debouncing."""
        # Cancel pending task for this document
        if document_id in self._pending_documents:
            self._pending_documents[document_id].cancel()

        # Update last content
        self._last_content[document_id] = plain_text

        # Schedule new task
        task = asyncio.create_task(
            self._debounced_generate(
                document_id=document_id,
                plain_text=plain_text,
                goal_context=goal_context,
                config=config,
                callback=callback
            )
        )
        self._pending_documents[document_id] = task

    async def generate_suggestions(
        self,
        document_id: int,
        plain_text: str,
        goal_context: Dict[str, Any],
        config: SuggestionConfig
    ) -> List[DocumentSuggestion]:
        """Generate AI suggestions for a document."""
        suggestions = []

        if not plain_text or len(plain_text.strip()) < 20:
            return suggestions

        # Generate different types of suggestions based on config
        if config.formatting:
            suggestions.extend(
                await self._generate_formatting_suggestions(plain_text, goal_context)
            )

        if config.content:
            suggestions.extend(
                await self._generate_content_suggestions(plain_text, goal_context)
            )

        if config.tasks:
            suggestions.extend(
                await self._generate_task_suggestions(plain_text, goal_context)
            )

        return suggestions

    async def _generate_formatting_suggestions(
        self,
        plain_text: str,
        goal_context: Dict[str, Any]
    ) -> List[DocumentSuggestion]:
        """Generate formatting suggestions."""
        suggestions = []

        # Check for basic formatting issues
        lines = plain_text.split("\n")

        # Check for very long paragraphs
        for i, line in enumerate(lines):
            if len(line) > 500 and not line.strip().startswith(("#", "-", "*", "```")):
                suggestions.append(DocumentSuggestion(
                    suggestion_type="formatting",
                    text="Consider breaking this long paragraph into smaller paragraphs for better readability.",
                    location=f"line {i + 1}",
                    confidence=0.7
                ))

        # Check for missing structure
        has_headers = any(line.strip().startswith("#") for line in lines)
        if len(plain_text) > 1000 and not has_headers:
            suggestions.append(DocumentSuggestion(
                suggestion_type="formatting",
                text="Consider adding section headers to organize your document.",
                confidence=0.6
            ))

        return suggestions[:3]  # Limit formatting suggestions

    async def _generate_content_suggestions(
        self,
        plain_text: str,
        goal_context: Dict[str, Any]
    ) -> List[DocumentSuggestion]:
        """Generate content suggestions using LLM."""
        suggestions = []

        goal_text = goal_context.get("goal_text", "")
        
        # Use LLM for intelligent content suggestions
        try:
            llm = LLMClient()
            model = get_model_name("ranker", default="openai:gpt-4o-mini")
            
            prompt = f"""You are reviewing a draft document written by someone working toward this goal: "{goal_text}"

DOCUMENT CONTENT:
{plain_text[:2000]}

Provide 2-3 specific, actionable suggestions to improve this document. Focus on:
1. How well it connects to their stated goal
2. Areas that need more depth or clarity
3. Missing elements that would strengthen the document

Return JSON array:
[
  {{
    "suggestion_type": "content",
    "text": "Specific suggestion text",
    "confidence": 0.8
  }}
]

Be direct and concise. Write suggestions as brief, actionable statements. Avoid verbose explanations or filler phrases. Return only valid JSON."""

            response = llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.7,
                max_tokens=500,
                json_top_level="array"
            )
            
            if isinstance(response, list):
                for item in response[:3]:  # Limit to 3
                    if isinstance(item, dict) and "text" in item:
                        suggestions.append(DocumentSuggestion(
                            suggestion_type=item.get("suggestion_type", "content"),
                            text=item.get("text", ""),
                            confidence=item.get("confidence", 0.7)
                        ))
        except Exception as e:
            print(f"[DocumentSuggestion] Error generating LLM suggestions: {e}")
            # Fallback to basic suggestions
            word_count = len(plain_text.split())
            if word_count < 50:
                suggestions.append(DocumentSuggestion(
                    suggestion_type="content",
                    text="Your document is quite short. Consider expanding on your main points.",
                    confidence=0.5
                ))

        return suggestions

    async def _generate_task_suggestions(
        self,
        plain_text: str,
        goal_context: Dict[str, Any]
    ) -> List[DocumentSuggestion]:
        """Generate learning task suggestions based on document content."""
        suggestions = []

        # Extract potential learning topics from the document
        topics = self._extract_learning_topics(plain_text)

        for topic in topics[:2]:  # Limit to 2 task suggestions
            suggestions.append(DocumentSuggestion(
                suggestion_type="task",
                text=f"Would you like to explore '{topic}' in more depth? This seems relevant to your writing.",
                confidence=0.5
            ))

        return suggestions

    def _extract_learning_topics(self, plain_text: str) -> List[str]:
        """Extract potential learning topics from text."""
        # Simple keyword extraction
        technical_terms = []

        # Look for code-related terms
        import re
        code_patterns = [
            r"\b(async|await|promise|callback)\b",
            r"\b(api|rest|graphql|endpoint)\b",
            r"\b(database|sql|query|schema)\b",
            r"\b(testing|test|unittest|pytest)\b",
            r"\b(deployment|docker|kubernetes)\b",
        ]

        for pattern in code_patterns:
            matches = re.findall(pattern, plain_text.lower())
            if matches:
                technical_terms.extend(matches)

        return list(set(technical_terms))

    async def generate_learning_tasks(
        self,
        document_content: str,
        goal_text: str,
        curriculum: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate background learning tasks based on document content."""
        tasks = []

        # Extract topics from document
        topics = self._extract_learning_topics(document_content)

        for topic in topics:
            task = {
                "topic": topic,
                "source": "document_analysis",
                "relevance": "Found in your current draft",
                "suggested_depth": "10min",
                "priority": "low",
            }

            # Check if topic relates to curriculum
            if curriculum and curriculum.get("steps"):
                for step in curriculum["steps"]:
                    if topic.lower() in step.get("objective", "").lower():
                        task["priority"] = "medium"
                        task["relevance"] = f"Related to curriculum step: {step['objective'][:50]}"
                        break

            tasks.append(task)

        return tasks[:5]  # Limit to 5 tasks


# Factory function
def create_document_suggestion_service(debounce_seconds: float = 2.0) -> DocumentSuggestionService:
    """Create a new document suggestion service."""
    return DocumentSuggestionService(debounce_seconds=debounce_seconds)


# Global instance
document_suggestion_service = DocumentSuggestionService()
