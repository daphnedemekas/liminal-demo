"""AI suggestions for documents — learning-aware version.

Generates suggestions that consider the user's prior knowledge, curiosity,
and learning goals. Aims to resolve uncertainty about what they understand,
identify confusion points, and balance curiosity/motivation with actual needs.
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, field

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.llm_client import LLMClient
from src.config import get_model_name


@dataclass
class DocumentSuggestion:
    """A single suggestion for a document."""
    suggestion_type: str  # "formatting", "content", "task", "learning_gap", "exploration"
    text: str
    location: Optional[str] = None
    confidence: float = 0.8
    learning_relevance: Optional[str] = None  # Why this matters for their learning
    prior_knowledge_level: Optional[str] = None  # What we think they already know
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SuggestionConfig:
    """Configuration for what suggestions to generate."""
    formatting: bool = True
    content: bool = True
    tasks: bool = False
    learning_aware: bool = True  # Use learning-aware suggestions
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
        if document_id in self._pending_documents:
            self._pending_documents[document_id].cancel()

        self._last_content[document_id] = plain_text

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

        if config.formatting:
            suggestions.extend(
                await self._generate_formatting_suggestions(plain_text, goal_context)
            )

        if config.content:
            suggestions.extend(
                await self._generate_content_suggestions(plain_text, goal_context, config.learning_aware)
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
        lines = plain_text.split("\n")

        for i, line in enumerate(lines):
            if len(line) > 500 and not line.strip().startswith(("#", "-", "*", "```")):
                suggestions.append(DocumentSuggestion(
                    suggestion_type="formatting",
                    text="Consider breaking this long paragraph into smaller paragraphs for better readability.",
                    location=f"line {i + 1}",
                    confidence=0.7
                ))

        has_headers = any(line.strip().startswith("#") for line in lines)
        if len(plain_text) > 1000 and not has_headers:
            suggestions.append(DocumentSuggestion(
                suggestion_type="formatting",
                text="Consider adding section headers to organize your document.",
                confidence=0.6
            ))

        return suggestions[:3]

    async def _generate_content_suggestions(
        self,
        plain_text: str,
        goal_context: Dict[str, Any],
        learning_aware: bool = True
    ) -> List[DocumentSuggestion]:
        """Generate content suggestions using LLM — learning-aware."""
        suggestions = []
        goal_text = goal_context.get("goal_text", "")
        user_profile = goal_context.get("user_profile", {})
        prior_knowledge = goal_context.get("prior_knowledge", "")
        teaching_context = goal_context.get("teaching_context", "")

        try:
            llm = LLMClient()
            model = get_model_name("ranker", default="openai:gpt-4o-mini")

            if learning_aware:
                prompt = f"""You are a learning-aware document advisor. You review documents written by someone actively learning.

THEIR LEARNING GOAL: "{goal_text}"
PRIOR KNOWLEDGE (what they likely already understand): {prior_knowledge or "Unknown — assess from their writing"}
TEACHING CONTEXT: {teaching_context or "General exploration"}

DOCUMENT CONTENT:
{plain_text[:2000]}

Your job is to help them learn through their writing. Analyze their document and provide 2-4 suggestions that:

1. RESOLVE UNCERTAINTY: Identify places where their writing reveals confusion or partial understanding. Point out specific concepts they seem to half-understand and suggest how to deepen that understanding.

2. IDENTIFY GAPS: Find concepts they reference but don't fully explain — these are likely knowledge gaps. Suggest they explore these more deeply.

3. BALANCE CURIOSITY AND NEED: Some suggestions should follow their apparent curiosity (what they seem excited about), and others should address what they actually need to understand (prerequisites, foundations they're missing).

4. BUILD ON WHAT THEY KNOW: Reference what they already demonstrate understanding of and suggest next steps that build on that foundation.

For each suggestion, also indicate:
- "learning_relevance": Why this matters for their learning journey (1 sentence)
- "prior_knowledge_level": What level of understanding their writing suggests ("confused", "partial", "solid", "expert")

Return JSON array:
[
  {{
    "suggestion_type": "learning_gap" | "content" | "exploration",
    "text": "Specific suggestion",
    "confidence": 0.8,
    "learning_relevance": "Why this matters",
    "prior_knowledge_level": "partial"
  }}
]

Be direct and concise. Return only valid JSON."""
            else:
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

Be direct and concise. Return only valid JSON."""

            response = llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.7,
                max_tokens=600,
                json_top_level="array"
            )

            if isinstance(response, list):
                for item in response[:4]:
                    if isinstance(item, dict) and "text" in item:
                        suggestions.append(DocumentSuggestion(
                            suggestion_type=item.get("suggestion_type", "content"),
                            text=item.get("text", ""),
                            confidence=item.get("confidence", 0.7),
                            learning_relevance=item.get("learning_relevance"),
                            prior_knowledge_level=item.get("prior_knowledge_level"),
                        ))
        except Exception as e:
            print(f"[DocumentSuggestion] Error generating LLM suggestions: {e}")
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
        topics = self._extract_learning_topics(plain_text)

        for topic in topics[:2]:
            suggestions.append(DocumentSuggestion(
                suggestion_type="task",
                text=f"Would you like to explore '{topic}' in more depth? This seems relevant to your writing.",
                confidence=0.5
            ))

        return suggestions

    def _extract_learning_topics(self, plain_text: str) -> List[str]:
        """Extract potential learning topics from text."""
        technical_terms = []
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
        topics = self._extract_learning_topics(document_content)

        for topic in topics:
            task = {
                "topic": topic,
                "source": "document_analysis",
                "relevance": "Found in your current draft",
                "suggested_depth": "10min",
                "priority": "low",
            }

            if curriculum and curriculum.get("steps"):
                for step in curriculum["steps"]:
                    if topic.lower() in step.get("objective", "").lower():
                        task["priority"] = "medium"
                        task["relevance"] = f"Related to curriculum step: {step['objective'][:50]}"
                        break

            tasks.append(task)

        return tasks[:5]


def create_document_suggestion_service(debounce_seconds: float = 2.0) -> DocumentSuggestionService:
    """Create a new document suggestion service."""
    return DocumentSuggestionService(debounce_seconds=debounce_seconds)


document_suggestion_service = DocumentSuggestionService()
