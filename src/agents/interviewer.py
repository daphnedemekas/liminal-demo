"""Interviewer agent for conducting natural conversation."""
from typing import List, Dict, Generator, Union
import random
import time
import re
from src.llm_client import LLMClient
from src.schema.full_schema import DiscoverySchema
from src.prompt_loader import PromptLoader
from src.config import get_model_name


class InterviewerAgent:
    """
    Conversational agent that asks questions and explores curiosity.

    The interviewer uses modular prompts that adapt based on:
    - Branch condition (what type of response user just gave)
    - User profile (curiosity type, pacing, etc.)
    - Current topic candidates and probing state
    - Suggested question from ranker
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize interviewer agent.

        Args:
            llm_client: LLM client for making API calls
        """
        self.llm = llm_client
        self.prompt_loader = PromptLoader()

    def get_opening_question(self, user_background: str = None) -> str:
        """
        Select opening question from bank based on user background.

        If user_background is provided, uses LLM to choose the most appropriate
        opening question. Otherwise, selects randomly.

        Args:
            user_background: User's background information from onboarding

        Returns:
            Opening question string
        """
        questions = self.prompt_loader.get_opening_questions()

        # If no background provided, fall back to random selection
        if not user_background:
            return random.choice(questions)

        # Use LLM to select and adapt best opening question based on user background
        selection_prompt = f"""You are selecting and adapting the best opening question for a curiosity discovery conversation.

USER BACKGROUND:
{user_background}

AVAILABLE OPENING QUESTIONS:
"""
        for i, q in enumerate(questions, 1):
            selection_prompt += f"\n{i}. {q}"

        selection_prompt += """

Based on the user's background, select the most appropriate opening question.

Instructions:
1. Choose the question that best fits their background
2. Return the question EXACTLY as written - do NOT modify it
3. Do NOT add "You mentioned..." or "Based on what you shared..." or any recap of their background
4. Do NOT paraphrase or repeat back what they told you
5. Just return the question directly

Return ONLY the selected question word-for-word, nothing else."""

        try:
            start = time.time()
            response = self.llm.chat(
                messages=[{"role": "user", "content": selection_prompt}],
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.5,  # Slightly higher for adaptation
                max_tokens=200
            ).strip()

            print(f"[TIMING] Opening question selection and adaptation: {time.time() - start:.2f}s")
            print(f"[Interviewer] Selected and adapted opening question based on user background")
            return response

        except Exception as e:
            print(f"[Interviewer] Error in question selection: {e}")
            # No fallback - re-raise to show error to user
            raise Exception(f"Opening question selection failed: {str(e)}")

    def generate_contextual_opening(self, user_background: str) -> str:
        """
        Generate a contextual opening question based on user's background.

        This analyzes their onboarding response and creates a personalized
        first question that shows you actually read what they wrote.

        Args:
            user_background: User's onboarding info

        Returns:
            Contextual opening question
        """
        contextual_prompt = f"""
You are a thought partner and curiosity architect. The user has shared their background.

USER_BACKGROUND:
{user_background}

TASK: Offer a compact insight about their interests, then ask ONE probing question about motivation.

STYLE
- Engaging, calm, concrete. No hype, no flattery.
- NEVER start with "Thanks for sharing" or any acknowledgment of what they said.
- Jump straight into substance.

CONTENT
- 1-2 sentences offering a SPECIFIC frame, distinction, or tension relevant to their interests
- Then ONE question probing the "why" behind their curiosity

FORMATTING (CRITICAL - you MUST do this):
Your response MUST have a blank line between the insight and the question.

CORRECT FORMAT:
In LLM design, there's a real tradeoff between making models more helpful (which risks sycophancy) and making them more accurate (which can feel colder).

Which side of that tradeoff feels more urgent to solve for you?

WRONG FORMAT (DO NOT DO THIS):
The intersection of X and Y is fascinating to explore. What draws you to it?

Include "\\n\\n" (two newlines) before your final question.

CONSTRAINTS
- Do NOT recap their background - they know what they said
- NEVER use: fascinating, interesting, compelling, profound, unique, intriguing
- NEVER start with "The intersection of X and Y..."
- Do NOT make up concepts - if you mention research or a framework, it should be real
- Be SPECIFIC - name actual mechanisms, not vague abstractions
- The insight should give them something to react to, not just validate them
"""

        try:
            start = time.time()
            response = self.llm.chat(
                messages=[{"role": "user", "content": contextual_prompt}],
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.7,
                max_tokens=200
            ).strip()

            print(f"[TIMING] Contextual opening generation: {time.time() - start:.2f}s")
            print(f"[Interviewer] Generated contextual opening based on user background")
            return response

        except Exception as e:
            print(f"[Interviewer] Error generating contextual opening: {e}")
            # No fallback - re-raise to show error to user
            raise Exception(f"Contextual opening generation failed: {str(e)}")

    def generate_goal_directed_opening(self, user_background: str, goal: str) -> str:
        """
        Generate a goal-directed opening question based on user's background and learning goal.

        This helps identify the best first step toward their stated goal by understanding
        where they are now and how they learn best.

        Args:
            user_background: User's onboarding info
            goal: User's stated learning goal

        Returns:
            Goal-directed opening question
        """
        goal_directed_prompt = f"""You are starting a goal-directed learning conversation. The user shared their background and a learning goal:

USER BACKGROUND:
{user_background}

LEARNING GOAL:
{goal}

YOUR TASK: Generate ONE opening question that helps identify the best FIRST STEP toward their goal.

CRITICAL RULES:
1. Output ONLY a question. No preamble, no observations, no acknowledgments.
2. Do NOT recap their background or goal.
3. Do NOT ask generic questions like "What do you already know about X?" or "Why are you interested in X?"
4. The question should help identify:
   - Where they are relative to the goal (what they understand vs. what's unclear)
   - What entry point would work best for them
   - What aspect of the goal is most relevant to their interests

QUESTION DESIGN:
- Assume they want to learn about {goal}
- Help identify whether they need conceptual foundations, practical skills, or specific techniques
- Ask about their relationship to the goal, not just their knowledge level
- Offer choices or contrasts when possible
- One question only, 1-2 sentences max

EXAMPLES:

Goal: "Learn jazz harmony"
Background: Classical piano, music theory basics, interested in improvisation
Question: "When you think about jazz harmony, are you more curious about understanding why the chord progressions work the way they do, or getting your hands to naturally find those sounds?"

Goal: "Understand vector calculus"
Background: Engineering student, solid algebra, physics applications
Question: "For vector calculus, are you more drawn to building geometric intuition for what the operators mean, or getting fluent with the computational techniques you'll need for physics?"

Goal: "Master chess endgames"
Background: Plays recreationally, loses in endgames, wants to improve
Question: "In the endgames you've played, is it more often that you don't know the winning plan, or you know it but struggle to execute accurately?"

Generate ONLY the question:"""

        try:
            start = time.time()
            response = self.llm.chat(
                messages=[{"role": "user", "content": goal_directed_prompt}],
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.7,
                max_tokens=200
            ).strip()

            print(f"[TIMING] Goal-directed opening generation: {time.time() - start:.2f}s")
            print(f"[Interviewer] Generated goal-directed opening for goal: {goal}")
            return response

        except Exception as e:
            print(f"[Interviewer] Error generating goal-directed opening: {e}")
            # No fallback - re-raise to show error to user
            raise Exception(f"Goal-directed opening generation failed: {str(e)}")

    def generate_next_question(
        self,
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """
        Generate next question based on current state.

        Uses modular prompts selected by conversation_mode or branch_condition.

        Args:
            schema: Current discovery schema
            conversation_history: Full conversation history

        Returns:
            Next question to ask
        """
        # conversation_mode determines which prompt to load
        # Valid modes: calibration, grounded_offer, hypothesis_correct, direct_probe, propose_tasks, negotiate_curriculum, topic_probe, explain_back, scenario_probe
        prompt_module = schema.controller.conversation_mode or "general_continuation"
        
        if not schema.controller.conversation_mode:
            print(f"[Interviewer] Warning: No conversation_mode set, using general_continuation")

        # Determine phase from schema
        phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"

        # Load appropriate prompt module with phase
        print(f"[Interviewer] Loading prompt: mode='{prompt_module}', phase='{phase}'")
        system_prompt = self.prompt_loader.load_interviewer_prompt(prompt_module, phase=phase)

        # Build context from schema for prompt formatting
        context = self._build_context(schema)

        # Format system prompt with context
        formatted_prompt = self._format_prompt(system_prompt, context)

        # Build messages
        messages = [{"role": "system", "content": formatted_prompt}]
        # Ensure the question generator always sees the full previous USER responses (user request),
        # while keeping assistant messages bounded to avoid token blowup.
        messages.extend(self._select_history_for_question(conversation_history))

        # Add runtime guidance (framework tracking, turn limits)
        guidance_parts = []
        guidance_parts.append(f"Turn {schema.interview_state.turns_elapsed + 1}. Frameworks offered so far: {schema.interview_state.frameworks_offered}/2.")

        if schema.interview_state.frameworks_offered >= 2:
            guidance_parts.append("You've reached the maximum frameworks - just ask questions now.")
        elif schema.interview_state.turns_elapsed < 2:
            guidance_parts.append("Too early for frameworks - just ask questions.")

        messages.append({
            "role": "user",
            "content": f"[Internal guidance: {' '.join(guidance_parts)}]"
        })

        # Generate response
        try:
            start = time.time()
            # Increase max_tokens for propose_tasks mode (needs 8-12 tasks with justifications)
            max_tokens = 2000 if prompt_module == "propose_tasks" else 500
            response = self.llm.chat(
                messages=messages,
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.8,  # Higher for natural conversation
                max_tokens=max_tokens
            ).strip()

            # Step 1: Strip any preamble (this is cheap and doesn't need regeneration)
            response = self._strip_preamble(response)

            # Step 2: Lint the cleaned question (skip for propose_tasks mode which generates curriculum, not questions)
            is_propose_tasks = prompt_module == "propose_tasks"
            is_valid, error = (True, "") if is_propose_tasks else self._lint_question(response)

            if not is_valid:
                print(f"[Interviewer] Question failed lint: {error}")
                print(f"[Interviewer] Failed question: {response}")

                # Try regenerating once with correction instruction
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": f"That question violated a rule: {error}. Generate a different question that avoids this issue. Return ONLY the question, no preamble."
                })

                response = self.llm.chat(
                    messages=messages,
                    model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                    temperature=0.8,
                    max_tokens=500
                ).strip()

                # Strip preamble from retry too
                response = self._strip_preamble(response)

                # Check again (but don't infinite loop)
                is_valid_retry, error_retry = self._lint_question(response)
                if not is_valid_retry:
                    print(f"[Interviewer] Retry also failed lint: {error_retry}")
                    print(f"[Interviewer] Continuing with imperfect question rather than failing")
                    # Don't crash - use the question anyway, it's better than nothing

            print(f"[TIMING] Interviewer question generation: {time.time() - start:.2f}s")

            return response

        except Exception as e:
            print(f"Error generating question: {e}")
            raise Exception(f"Question generation failed: {str(e)}")

    def generate_next_question_stream(
        self,
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """
        Stream the next question, yielding chunks as they arrive.
        
        This is a streaming version of generate_next_question for better UX.
        Includes early detection for banned phrases - if found, falls back to
        non-streaming generation with lint/retry.
        
        Args:
            schema: Current discovery schema
            conversation_history: Full conversation history
            
        Yields:
            Text chunks as they stream in
        """
        # conversation_mode determines which prompt to load
        prompt_module = schema.controller.conversation_mode or "general_continuation"

        # Determine phase from schema
        phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"

        # Load appropriate prompt module with phase
        system_prompt = self.prompt_loader.load_interviewer_prompt(prompt_module, phase=phase)

        # Build context from schema for prompt formatting
        context = self._build_context(schema)

        # Format system prompt with context
        formatted_prompt = self._format_prompt(system_prompt, context)

        # Build messages
        messages = [{"role": "system", "content": formatted_prompt}]
        messages.extend(self._select_history_for_question(conversation_history))

        # Add runtime guidance (framework tracking, turn limits)
        guidance_parts = []
        guidance_parts.append(f"Turn {schema.interview_state.turns_elapsed + 1}. Frameworks offered so far: {schema.interview_state.frameworks_offered}/2.")

        if schema.interview_state.frameworks_offered >= 2:
            guidance_parts.append("You've reached the maximum frameworks - just ask questions now.")
        elif schema.interview_state.turns_elapsed < 2:
            guidance_parts.append("Too early for frameworks - just ask questions.")

        messages.append({
            "role": "user",
            "content": f"[Internal guidance: {' '.join(guidance_parts)}]"
        })

        # Stream the response with early banned-phrase detection
        try:
            buffer = ""
            buffer_threshold = 80  # Check for banned phrases after this many chars
            started_streaming = False
            
            for chunk in self.llm.chat_stream(
                messages=messages,
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.8,
                max_tokens=500
            ):
                buffer += chunk
                
                # Early detection: check for banned phrases in buffer before streaming
                if not started_streaming and len(buffer) >= buffer_threshold:
                    print(f"[STREAM DEBUG] Checking buffer ({len(buffer)} chars): '{buffer[:100]}...'")
                    has_banned = self._check_early_banned_phrases(buffer)
                    if has_banned:
                        print(f"[Interviewer] Early banned phrase detected in stream, falling back to non-streaming with retry")
                        # Fall back to non-streaming with lint/retry
                        fallback_response = self.generate_next_question(schema, conversation_history)
                        yield fallback_response
                        return
                    else:
                        print(f"[STREAM DEBUG] Buffer passed early check, starting stream")
                    
                    # No banned phrases found, start streaming the buffer
                    started_streaming = True
                    yield buffer
                    buffer = ""
                elif started_streaming:
                    yield chunk
            
            # Yield any remaining buffer if we never hit the threshold
            if not started_streaming and buffer:
                # Check final buffer
                has_banned = self._check_early_banned_phrases(buffer)
                if has_banned:
                    print(f"[Interviewer] Banned phrase detected, falling back to non-streaming")
                    fallback_response = self.generate_next_question(schema, conversation_history)
                    yield fallback_response
                    return
                yield buffer
                
        except Exception as e:
            print(f"Error streaming question: {e}")
            # No fallback - re-raise to show error to user
            raise Exception(f"Question streaming failed: {str(e)}")

    def _extract_curriculum_tasks(self, response: str) -> List[Dict]:
        """
        Parse curriculum tasks from interviewer's natural language response.

        Expected format:
        1. Topic Name - Description. Why for you: justification
        2. Another Topic - Description. Why for you: justification

        Args:
            response: The generated response with curriculum

        Returns:
            List of task dicts with id, topic, justification, prerequisites, status
        """
        tasks = []

        # Regex pattern to match numbered items with topic and description
        # Matches: "1. Topic - Description" or "1. Topic"
        pattern = r'(\d+)\.\s+(.+?)(?:\s+-\s+(.+?))?(?=\n\d+\.|\nWhy for you:|Why for you:|$)'
        matches = re.finditer(pattern, response, re.DOTALL | re.IGNORECASE)

        for match in matches:
            task_id = int(match.group(1))
            topic = match.group(2).strip()
            description = match.group(3).strip() if match.group(3) else ""

            # Extract "Why for you" justification if present
            justification = ""
            # Look for "Why for you:" after this task number and before the next task
            why_pattern = rf'{task_id}\..+?Why for you:\s*(.+?)(?=\n\d+\.|$)'
            why_match = re.search(why_pattern, response, re.DOTALL | re.IGNORECASE)
            if why_match:
                justification = why_match.group(1).strip()
                # Clean up - remove leading/trailing whitespace and newlines
                justification = ' '.join(justification.split())

            # If no justification found, use description as fallback
            if not justification and description:
                justification = description

            tasks.append({
                "id": task_id,
                "topic": topic,
                "description": description,
                "justification": justification if justification else f"Explore {topic}",
                "prerequisites": [],  # Will be set based on order
                "status": "locked" if task_id > 1 else "available"
            })

        # Set prerequisites based on sequential order
        for i, task in enumerate(tasks):
            if i > 0:
                task["prerequisites"] = [tasks[i-1]["id"]]

        print(f"[Interviewer] Extracted {len(tasks)} tasks from curriculum proposal")
        if len(tasks) == 0:
            print(f"[Interviewer] DEBUG: Failed to extract tasks. Response preview (first 500 chars):")
            print(f"[Interviewer] {response[:500]}")
            print(f"[Interviewer] Testing regex pattern...")
            # Test if there are ANY numbered items at all
            simple_pattern = r'(\d+)\.'
            simple_matches = re.findall(simple_pattern, response)
            if simple_matches:
                print(f"[Interviewer] Found {len(simple_matches)} numbered items: {simple_matches[:10]}")
            else:
                print(f"[Interviewer] No numbered items found at all!")
        else:
            for task in tasks:
                print(f"  - Task {task['id']}: {task['topic']}")

        return tasks

    def generate_response(
        self,
        user_message: str,
        schema: DiscoverySchema,
        conversation_history: List[Dict]
    ) -> Union[str, Dict]:
        """
        Generate interviewer response.

        This is the main entry point that replaces generate_next_question for
        cases where we need to detect curriculum proposals.

        Args:
            user_message: User's message
            schema: Current discovery schema
            conversation_history: Full conversation history

        Returns:
            - str: Regular conversation message
            - Dict: Structured response for curriculum proposal
                {
                    "type": "curriculum_proposal",
                    "text": "...",
                    "tasks": [...],
                    "goal": "..."
                }
        """
        # Generate the response using the existing question generation logic
        response = self.generate_next_question(schema, conversation_history)

        # BETTER: Check controller mode instead of parsing text
        # If controller forced propose_tasks mode, we know it's proposing curriculum
        # negotiate_curriculum mode should return a regular clarifying question, not extract curriculum
        is_proposing_curriculum = schema.controller.conversation_mode == "propose_tasks"
        is_negotiating_curriculum = schema.controller.conversation_mode == "negotiate_curriculum"

        if is_negotiating_curriculum:
            print("[Interviewer] Controller in negotiate_curriculum mode - returning clarifying question")
            # Return regular response - a clarifying question about curriculum modifications
            return response

        if is_proposing_curriculum:
            print("[Interviewer] Controller in propose_tasks mode - parsing curriculum from response")

            # Extract tasks from the response
            tasks = self._extract_curriculum_tasks(response)

            if len(tasks) == 0:
                print("[Interviewer] WARNING: propose_tasks mode but no tasks extracted from response")
                print(f"[Interviewer] Response text: {response[:200]}...")
                
                # CRITICAL: LLM didn't follow the prompt - retry with explicit instruction
                print("[Interviewer] LLM ignored propose_tasks prompt. Retrying with explicit curriculum instruction...")
                
                # Build explicit retry prompt
                context = self._build_context(schema)
                retry_prompt = f"""You MUST generate a curriculum with 8-12 numbered tasks. Your previous response was a question, but you need to propose a learning path instead.

Generate a numbered list of 8-12 tasks in this exact format:

1. [Task Name] - [Brief description]
   Why for you: [Personalized justification]

2. [Task Name] - [Brief description]
   Why for you: [Personalized justification]

... (continue for 8-12 tasks total)

End with: "This is my best guess at the complete journey. We can adjust this as we go based on what works for you."

Goal: {context.get('user_goal', '')}
Teaching candidates: {', '.join([tc.get('topic', '') for tc in context.get('teaching_candidates', [])])}

Generate the curriculum now:"""
                
                # Retry with explicit instruction
                retry_messages = [
                    {"role": "system", "content": self.prompt_loader.load_interviewer_prompt("propose_tasks", phase="teaching_discovery")},
                    {"role": "user", "content": retry_prompt}
                ]
                
                retry_response = self.llm.chat(
                    messages=retry_messages,
                    model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                    temperature=0.7,  # Lower temperature for more structured output
                    max_tokens=2000
                ).strip()
                
                print(f"[Interviewer] Retry response preview: {retry_response[:300]}...")
                
                # Try extracting from retry
                tasks = self._extract_curriculum_tasks(retry_response)
                
                if len(tasks) > 0:
                    print(f"[Interviewer] Retry successful - extracted {len(tasks)} tasks")
                    response = retry_response  # Use the retry response
                elif len(schema.teaching_candidates) > 0:
                    # Still failed - expand teaching candidates to 8-12 tasks
                    print(f"[Interviewer] Retry also failed. Expanding {len(schema.teaching_candidates)} teaching candidates to 8-12 tasks")
                    # Generate additional tasks based on the goal
                    goal = context.get('user_goal', '')
                    base_topics = [tc.topic for tc in schema.teaching_candidates]
                    
                    # Create 8-12 tasks by expanding from teaching candidates
                    tasks = []
                    for i in range(12):  # Generate up to 12 tasks
                        if i < len(base_topics):
                            topic = base_topics[i]
                        else:
                            # Generate synthetic topics based on goal
                            topic = f"Advanced aspect {i+1} of {goal}"
                        
                        tasks.append({
                            "id": i + 1,
                            "topic": topic,
                            "justification": f"Essential step {i+1} toward achieving your goal",
                            "prerequisites": [i] if i > 0 else [],
                            "status": "available" if i == 0 else "locked"
                        })
                    
                    # Update response to include the curriculum text
                    response = f"Based on your goal '{goal}' and what I've learned about your background, here's a complete learning path I've designed for you:\n\n" + "\n".join([f"{t['id']}. {t['topic']}\n   Why for you: {t['justification']}" for t in tasks]) + "\n\nThis is my best guess at the complete journey. We can adjust this as we go based on what works for you."
                else:
                    # Really can't extract anything - return regular response
                    print("[Interviewer] ERROR: Cannot generate curriculum even after retry")
                    return response

            # Validate task count
            if len(tasks) < 8:
                print(f"[Interviewer] WARNING: Only {len(tasks)} tasks extracted, but need 8-12. Expanding to 8 tasks...")
                # Expand to at least 8 tasks
                while len(tasks) < 8:
                    next_id = len(tasks) + 1
                    goal = schema.interview_state.user_goal or "your learning goal"
                    tasks.append({
                        "id": next_id,
                        "topic": f"Additional learning step {next_id}",
                        "justification": f"Essential component {next_id} for achieving {goal}",
                        "prerequisites": [next_id - 1] if next_id > 1 else [],
                        "status": "locked"
                    })

            print(f"[Interviewer] Extracted {len(tasks)} tasks from curriculum")

            return {
                "type": "curriculum_proposal",
                "text": response,
                "tasks": tasks,
                "goal": schema.interview_state.user_goal
            }

        # Regular message
        return response

    def _check_early_banned_phrases(self, text: str) -> bool:
        """
        Quick check for banned phrases during streaming.
        
        Returns True if a banned phrase is detected.
        """
        # Most common recall-pressure and parroting phrases
        early_banned = [
            "what are you curious about",
            "what have you been curious about",
            "what have you been drawn to",
            "what have you been interested in",
            "what topics interest you",
            "what interests you",
            "that's so interesting",
            "that's really interesting",
            "that's fascinating",
            "you mentioned",
            "you've explored",
            "you've mentioned",
            "so what you're saying",
            "it sounds like you",
            "based on what you shared",
            "given your interest in",
            "given your background",
            "you're exploring",  # Added - catches "You're exploring the intersection..."
            "you're navigating",
        ]
        
        text_lower = text.lower()
        for phrase in early_banned:
            if phrase in text_lower:
                print(f"[LINT] Early banned phrase detected: '{phrase}' in text: '{text[:100]}...'")
                return True
        return False

    def contains_framework(self, response: str) -> bool:
        """
        Detect if a response contains a cognitive framework.

        Simple heuristic based on common framework language.

        Args:
            response: The generated question/response

        Returns:
            True if framework detected
        """
        framework_indicators = [
            "cognitive science",
            "researchers",
            "research shows",
            "framework",
            "psychologists",
            "studies show",
            "there's this distinction",
            "that's a tension",
            "cognitive scientists",
            "learning science"
        ]

        response_lower = response.lower()
        return any(indicator in response_lower for indicator in framework_indicators)

    def _lint_question(self, question: str) -> tuple:
        """
        Check if a generated question passes quality checks.
        
        Args:
            question: The generated question text
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        import re
        
        # Rule 1: Exactly one question mark
        q_count = len(re.findall(r'\?', question))
        if q_count == 0:
            return False, "No question mark found - must ask a question"
        if q_count > 1:
            return False, "Multiple question marks - ask ONE clear question"
        
        # Rule 2: Truly bad questions (recall-pressure, sycophancy) - these need regeneration
        bad_question_phrases = [
            # Recall-pressure questions (explicitly ask user to invent/remember)
            "what are you curious about",
            "what have you been curious about",
            "what have you been drawn to",
            "what have you been interested in",
            "what topics interest you",
            "what interests you",
            "tell me about a time",
            "can you think of",
            "what comes to mind",
            # Empty validation / sycophancy
            "that's so interesting",
            "that's really interesting", 
            "that's fascinating",
            "great point",
            "i love that",
            "wonderful",
        ]
        
        question_lower = question.lower()
        for phrase in bad_question_phrases:
            if phrase in question_lower:
                print(f"[LINT] Question failed: contains bad phrase '{phrase}'")
                return False, f"Contains bad phrase: '{phrase}'"
        
        # Rule 3: Must not be too short (likely incomplete)
        if len(question.strip()) < 20:
            return False, "Question too short - needs more context"
        
        # Note: No length cap - longer contextual questions with grounding content are good
        
        return True, ""

    def _strip_preamble(self, question: str) -> str:
        """
        Detect and strip preamble phrases from a question.
        
        Preambles are filler like "You mentioned...", "Given your interest in...",
        "You're working on..." - they come BEFORE the actual question and can be removed.
        
        Returns the cleaned question.
        """
        import re
        
        # Preamble patterns - these typically precede the actual question
        preamble_patterns = [
            # Parroting / echoing user
            r"^you(?:'ve)?\s+mentioned[^?]*?,\s*",
            r"^you(?:'ve)?\s+explored[^?]*?,\s*",
            r"^you(?:'ve)?\s+shared[^?]*?,\s*",
            r"^you\s+said[^?]*?,\s*",
            r"^so\s+what\s+you(?:'re)?\s+saying\s+is[^?]*?,\s*",
            r"^it\s+sounds\s+like\s+you[^?]*?,\s*",
            r"^based\s+on\s+what\s+you(?:'ve)?\s+shared[^?]*?,\s*",
            r"^given\s+your\s+(?:interest|background)\s+in[^?]*?,\s*",
            # Recap preambles
            r"^you(?:'re)?\s+navigating[^?]*?,\s*",
            r"^you(?:'re)?\s+working\s+on[^?]*?,\s*",
            r"^you(?:'re)?\s+exploring[^?]*?,\s*",
            r"^since\s+you(?:'re|'ve)[^?]*?,\s*",
        ]
        
        original = question
        question_lower = question.lower()
        
        # Words that indicate the remaining text is grammatically dependent on the preamble
        # If stripping leaves one of these at the start, DON'T strip
        dependent_starters = [
            'especially', 'particularly', 'in particular', 'specifically',
            'and', 'but', 'or', 'nor', 'yet', 'so',  # conjunctions
            'which', 'who', 'that', 'where', 'when',  # relative pronouns
            'this', 'these', 'it',  # demonstratives pointing back
            'like', 'such as', 'as',  # comparative/exemplifying words
            'for', 'to', 'by', 'with', 'from',  # prepositions
            'into', 'through', 'about',  # more prepositions
        ]
        
        for pattern in preamble_patterns:
            match = re.match(pattern, question_lower, re.IGNORECASE)
            if match:
                # Found a preamble - strip it
                preamble_end = match.end()
                stripped = question[preamble_end:].strip()
                
                # Check if the remaining text starts with a dependent word
                stripped_lower = stripped.lower()
                is_dependent = any(stripped_lower.startswith(word) for word in dependent_starters)
                
                if is_dependent:
                    print(f"[LINT] Preamble found but remaining text is dependent, keeping original")
                    return original
                
                # Make sure we still have a valid question after stripping
                if '?' in stripped and len(stripped) > 15:
                    # Capitalize first letter
                    stripped = stripped[0].upper() + stripped[1:] if stripped else stripped
                    print(f"[LINT] Stripped preamble: '{question[:preamble_end].strip()}'")
                    print(f"[LINT] Clean question: '{stripped}'")
                    return stripped
        
        return original

    def _select_history_for_question(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Keep all user turns, but only the last few assistant turns.

        This satisfies "include the full previous responses" while still keeping latency bounded.
        """
        max_assistant_msgs = 6
        assistant_msgs: List[Dict[str, str]] = []
        user_msgs: List[Dict[str, str]] = []

        for msg in history:
            if msg.get("role") == "user":
                user_msgs.append(msg)
            elif msg.get("role") == "assistant":
                assistant_msgs.append(msg)

        trimmed_assistant = assistant_msgs[-max_assistant_msgs:]

        # Reconstruct in original order
        assistant_set = {id(m) for m in trimmed_assistant}
        selected: List[Dict[str, str]] = []
        for msg in history:
            if msg.get("role") == "user":
                selected.append(msg)
            elif msg.get("role") == "assistant" and id(msg) in assistant_set:
                selected.append(msg)
        return selected

    def _build_context(self, schema: DiscoverySchema) -> Dict:
        """
        Build context dictionary for prompt formatting.

        Only includes relevant parts of schema, not everything.

        Args:
            schema: Discovery schema

        Returns:
            Context dictionary for formatting
        """
        # Get top teaching candidates by readiness score (primary)
        top_teaching = sorted(
            schema.teaching_candidates,
            key=lambda t: t.readiness_score,
            reverse=True
        )[:3]

        # Get top conversational themes as backup context
        top_themes = sorted(
            schema.conversational_themes,
            key=lambda t: t.readiness_score,
            reverse=True
        )[:3]

        # Extract prior knowledge assessment data for propose_tasks prompt
        prior_knowledge = schema.prior_knowledge_assessment
        
        # Get concept knowledge as strings
        concepts_known = []
        concepts_unclear = []
        if prior_knowledge.concept_knowledge:
            for ck in prior_knowledge.concept_knowledge:
                # Handle both string format (legacy) and ConceptKnowledge object format
                if isinstance(ck, str):
                    concepts_known.append(ck)
                elif hasattr(ck, 'concept'):
                    # Get proficiency - might be string or enum
                    prof = getattr(ck, 'proficiency', None)
                    if prof:
                        prof_str = prof.value if hasattr(prof, 'value') else str(prof)
                        concepts_known.append(f"{ck.concept} ({prof_str})")
                    else:
                        concepts_known.append(ck.concept)
        elif prior_knowledge.concepts_known:
            concepts_known = prior_knowledge.concepts_known
        if prior_knowledge.concepts_unclear:
            concepts_unclear = prior_knowledge.concepts_unclear

        return {
            "user_curiosity_type": schema.user_profile.curiosity_type.value or "unknown",
            "user_pacing": schema.user_profile.pacing_preference.value or "unknown",
            "user_uncertainty_tolerance": schema.user_profile.uncertainty_tolerance.value or "unknown",
            "focus_instruction": schema.controller.focus_instruction or "",
            "question_intent": schema.controller.question_intent or "",
            "target_ambiguity": schema.controller.target_ambiguity or "",
            "conversation_mode": schema.controller.conversation_mode or "",
            "user_goal": schema.interview_state.user_goal or "",
            "teaching_candidates": [
                {
                    "topic": c.topic,
                    "focus_question": c.focus_question,
                    "gap": c.identified_gap,
                    "readiness": c.readiness_score
                }
                for c in top_teaching
            ],
            "conversational_themes": [
                {
                    "theme": c.theme_seed,
                    "type": c.theme_type,
                    "hook": c.disambiguated_hook,
                    "readiness": c.readiness_score
                }
                for c in top_themes
            ],
            "ready_for_teach": schema.teaching_recommendation.ready,
            "turns_elapsed": schema.interview_state.turns_elapsed,
            "topics_mentioned": schema.interview_state.topics_mentioned,
            "frameworks_offered": schema.interview_state.frameworks_offered,
            # Prior knowledge assessment data for propose_tasks prompt
            "assessed_level": prior_knowledge.assessed_level or "intermediate",
            "concepts_known": ", ".join(concepts_known) if concepts_known else "Not yet assessed",
            "concepts_unclear": ", ".join(concepts_unclear) if concepts_unclear else "Not yet identified",
            "practical_experience": prior_knowledge.practical_experience or "Not yet assessed",
            "learning_style_hints": ", ".join(prior_knowledge.learning_style_hints) if prior_knowledge.learning_style_hints else "Not yet identified",
            # Current curriculum tasks (for modification clarification) - formatted as string
            "current_curriculum_tasks": "\n".join([
                f"{t.id}. {t.topic}\n   Justification: {t.justification}"
                for t in schema.task_curriculum.tasks
            ]) if schema.task_curriculum and schema.task_curriculum.tasks else "No curriculum tasks yet"
        }

    def _format_prompt(self, prompt_template: str, context: Dict) -> str:
        """
        Format prompt with context variables.

        Replaces {variable} with context values. Uses safe substitution
        to avoid errors if variables are missing.

        Args:
            prompt_template: Prompt with {variable} placeholders
            context: Dictionary of values

        Returns:
            Formatted prompt
        """
        try:
            # Use .format() with safe handling of missing keys
            # Convert context keys to handle missing values gracefully
            class SafeDict(dict):
                def __missing__(self, key):
                    return '{' + key + '}'  # Return placeholder if missing
            
            safe_context = SafeDict(context)
            # Use .format() which handles {var} syntax natively
            return prompt_template.format(**safe_context)
        except Exception as e:
            print(f"[Interviewer] Error formatting prompt: {e}")
            # If formatting fails, return original
            return prompt_template
