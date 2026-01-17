"""Learning engine for the 3-step learning phase."""
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.llm_client import LLMClient
from src.models.analysis import FinalTopic
from src.config import get_prompts_dir


class LearningEngine:
    """Manages the 3-step learning phase: assess → identify → explain."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.state = "not_started"  # not_started, assess, identify, explain, complete
        self.final_topic: Optional[FinalTopic] = None
        self.confusion_identified: Optional[str] = None
        self.turn_count = 0

        # Load learning tutor prompt
        prompts_dir = get_prompts_dir()
        prompt_path = prompts_dir / "learning_tutor_system.txt"

        if prompt_path.exists():
            with open(prompt_path, 'r') as f:
                self.base_prompt = f.read()
        else:
            # Fallback inline prompt if file doesn't exist yet
            self.base_prompt = self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Default prompt if file doesn't exist."""
        return """You are a tutor helping someone understand a specific topic they're confused about.

CONTEXT:
Topic: {topic}
What they know: {prior_knowledge_summary}
Their confusion: {user_confusion}
Why they care: {stakes}

YOUR GOAL (3 steps):
1. ASSESS: Ask 2-3 questions to understand what they already know vs what confuses them
2. IDENTIFY: Pinpoint the exact concept/principle causing confusion
3. EXPLAIN: Provide a clear, tailored explanation targeting that confusion

STYLE:
- Direct and conversational
- Use examples relevant to their background
- Check understanding incrementally
- One concept at a time

CURRENT STEP: {step}

{step_instructions}"""

    def start_learning(self, final_topic: FinalTopic) -> str:
        """Initialize learning phase with discovered topic."""
        self.final_topic = final_topic
        self.state = "assess"
        self.turn_count = 0

        # Generate opening question for assessment
        return f"Let's explore {final_topic.topic}. What do you already understand about it?"

    def process_message(self, user_input: str, conversation_history: List[Dict]) -> Dict:
        """
        Process user message and return response based on current state.

        Returns:
            {
                "response": str,
                "state": str,
                "confusion_identified": Optional[str],
                "explanation_complete": bool
            }
        """
        self.turn_count += 1

        # Build system prompt based on current state
        system_prompt = self._build_system_prompt()

        # Build messages for LLM
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation history (last 10 messages to keep context manageable)
        messages.extend(conversation_history[-10:])

        # Get response from LLM
        response = self.llm_client.chat(
            messages=messages,
            model="claude-sonnet-4-20250514",
            temperature=0.7,
            max_tokens=1000
        )

        # Determine state transitions
        new_state, confusion, complete = self._determine_state_transition(
            response,
            user_input
        )

        self.state = new_state
        if confusion:
            self.confusion_identified = confusion

        return {
            "response": response,
            "state": self.state,
            "confusion_identified": self.confusion_identified,
            "explanation_complete": complete
        }

    def _build_system_prompt(self) -> str:
        """Build system prompt based on current state."""
        if not self.final_topic:
            return self.base_prompt

        # Format base prompt with topic context
        prior_knowledge = f"Score: {self.final_topic.scores.prior_knowledge}/5"
        step_instructions = self._get_step_instructions()

        prompt = self.base_prompt.format(
            topic=self.final_topic.topic,
            prior_knowledge_summary=prior_knowledge,
            user_confusion=self.final_topic.user_confusion,
            stakes=self.final_topic.stakes,
            step=self.state,
            step_instructions=step_instructions
        )

        return prompt

    def _get_step_instructions(self) -> str:
        """Get specific instructions for current step."""
        if self.state == "assess":
            return """ASSESS STEP:
- Ask what they already understand about the topic
- Listen for gaps in their knowledge
- Identify what's unclear vs what's clear
- After 2-3 exchanges, move to IDENTIFY step"""

        elif self.state == "identify":
            return """IDENTIFY STEP:
- Based on what they've said, pinpoint the specific confusion
- Ask clarifying questions to narrow it down
- State what you believe is confusing them
- Get confirmation before explaining
- Once confirmed, move to EXPLAIN step"""

        elif self.state == "explain":
            return """EXPLAIN STEP:
- Provide a clear, targeted explanation
- Use examples relevant to their background
- Check understanding incrementally
- Answer follow-up questions
- Once they understand, acknowledge completion"""

        else:
            return ""

    def _determine_state_transition(
        self,
        response: str,
        user_input: str
    ) -> tuple[str, Optional[str], bool]:
        """
        Determine if we should transition to next state.

        Returns:
            (new_state, confusion_identified, explanation_complete)
        """
        confusion = self.confusion_identified
        complete = False

        # Simple heuristic-based state transitions
        # In production, you might want a more sophisticated approach

        if self.state == "assess":
            # After 2-3 turns in assess, move to identify
            if self.turn_count >= 2:
                return "identify", confusion, False

        elif self.state == "identify":
            # If response contains phrases indicating identified confusion
            identifying_phrases = [
                "the confusing part",
                "what's unclear",
                "where you're stuck",
                "the tricky bit",
                "seems like",
                "sounds like"
            ]

            if any(phrase in response.lower() for phrase in identifying_phrases):
                # Extract the confusion (simplified - just use the response)
                confusion = response
                return "explain", confusion, False

            # After 3 turns in identify, force transition
            if self.turn_count >= 5:
                return "explain", confusion or "General confusion about the topic", False

        elif self.state == "explain":
            # Check if explanation seems complete
            completion_phrases = [
                "makes sense",
                "got it",
                "understand now",
                "that helps",
                "thank you"
            ]

            if any(phrase in user_input.lower() for phrase in completion_phrases):
                complete = True
                return "complete", confusion, True

            # After extended explanation, consider it complete
            if self.turn_count >= 8:
                complete = True
                return "complete", confusion, True

        return self.state, confusion, complete
