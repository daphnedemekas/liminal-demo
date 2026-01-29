"""Interviewer agent for conducting natural conversation."""
from typing import List, Dict, Generator, Union, Optional
from pathlib import Path
import random
import time
import re
from src.llm_client import LLMClient
from src.schema.full_schema import DiscoverySchema
from src.prompt_loader import PromptLoader
from src.config import get_model_name
from src.prompt.assembly import assemble_prompt
from src.prompt.gather import gather_conversation


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
        # Get repo root for prompt assembly
        project_root = Path(__file__).parent.parent.parent
        self.repo_root = project_root

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

    def generate_goal_directed_opening(self, user_background: str, goal: str, exploration_context: Optional[List[Dict[str, str]]] = None) -> str:
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
        # Format exploration context if available
        exploration_context_str = ""
        if exploration_context and len(exploration_context) > 0:
            exploration_text = gather_conversation(exploration_context, max_messages=10, max_chars=1500)
            if exploration_text:
                exploration_context_str = f"""

EXPLORATION CONVERSATION (where this goal came from):
{exploration_text}

IMPORTANT: This goal emerged from the exploration conversation above. Use this context to:
- Avoid asking questions that were already asked in exploration
- Build on what was already discussed
- Reference specific things they mentioned if relevant
- Continue the conversation naturally, don't repeat what was already covered
"""
        
        goal_directed_prompt = f"""You are starting a goal-directed learning conversation. The user shared their background and a learning goal:

USER BACKGROUND:
{user_background}

LEARNING GOAL:
{goal}{exploration_context_str}

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
- Focus on understanding their background, motivation, or starting point
- One question only, 1-2 sentences max

PREFERRED QUESTION TYPES:
- Background/prior knowledge: "What's your current experience with [aspect of goal]?"
- Motivation/stakes: "What's driving your interest in [goal]? Is there a specific situation or problem you're trying to solve?"
- Concerns/uncertainties: "What aspect of [goal] feels most uncertain or challenging to you right now?"
- Starting point: "Where would you say you're starting from with [goal]? What do you already understand, and what feels like the biggest gap?"

EXAMPLES:

Goal: "Learn jazz harmony"
Background: Classical piano, music theory basics, interested in improvisation
Question: "What's your current experience with jazz harmony? Are you coming in fresh, or do you have some background with chord progressions?"

Goal: "Understand vector calculus"
Background: Engineering student, solid algebra, physics applications
Question: "What's driving your interest in vector calculus? Is there a specific physics problem or application you're trying to solve?"

Goal: "Master chess endgames"
Background: Plays recreationally, loses in endgames, wants to improve
Question: "What aspect of chess endgames feels most uncertain or challenging to you right now?"

AVOID:
- Forced-choice questions ("are you more curious about X or Y?")
- Questions that ask them to choose between two options
- Questions that assume they must pick one direction

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
        # Valid modes: explore_deeper, provide_perspective, resolve_confusion, suggest_candidate, answer_question, general_continuation
        # Legacy modes: calibration, grounded_offer, hypothesis_correct, direct_probe, propose_tasks, negotiate_curriculum, topic_probe, explain_back, scenario_probe
        prompt_module = schema.controller.conversation_mode or "general_continuation"
        
        # Safety check: propose_tasks should only be set via manual button click
        # Allow propose_tasks if next_action is "propose_task_curriculum" (set by generate_learning_path)
        # This indicates manual curriculum generation is in progress
        is_manual_generation = (
            prompt_module == "propose_tasks" and 
            schema.controller.next_action == "propose_task_curriculum"
        )
        
        if prompt_module == "propose_tasks" and not schema.task_curriculum.proposed and not is_manual_generation:
            print(f"[INTERVIEWER] WARNING: propose_tasks mode detected without curriculum proposed - switching to general_continuation")
            print(f"[INTERVIEWER] Curriculum generation is manual-only via button")
            prompt_module = "general_continuation"
        
        if not schema.controller.conversation_mode:
            print(f"[Interviewer] Warning: No conversation_mode set, using general_continuation")

        # Determine phase from schema
        phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"

        # Load appropriate prompt module with phase
        print(f"[Interviewer] Loading prompt: mode='{prompt_module}', phase='{phase}'")
        
        # Use assemble_prompt to build system prompt with context
        formatted_prompt, dropped = assemble_prompt(
            step_name=prompt_module,
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            schema_state=schema,
            conversation_history=conversation_history,
            task="interviewer",
            phase=phase,
        )

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
        # Check controller mode first
        # propose_tasks should only be set via manual button click (generate_learning_path)
        is_proposing_curriculum = schema.controller.conversation_mode == "propose_tasks"
        is_negotiating_curriculum = schema.controller.conversation_mode == "negotiate_curriculum"
        
        # Safety check: if propose_tasks is set without curriculum being proposed, something went wrong
        # BUT allow it if next_action is "propose_task_curriculum" (manual generation in progress)
        is_manual_generation = (
            is_proposing_curriculum and 
            schema.controller.next_action == "propose_task_curriculum"
        )
        
        if is_proposing_curriculum and not schema.task_curriculum.proposed and not is_manual_generation:
            print(f"[INTERVIEWER] WARNING: propose_tasks mode detected without curriculum proposed - treating as regular conversation")
            is_proposing_curriculum = False

        if is_negotiating_curriculum:
            # If next_action is propose_task_curriculum, user wants to regenerate curriculum with modifications
            if schema.controller and schema.controller.next_action == "propose_task_curriculum":
                print("[Interviewer] Controller in negotiate_curriculum mode with propose_task_curriculum - regenerating curriculum with modifications")
                # Regenerate curriculum incorporating user's modification request
                return self._generate_curriculum_proposal_json(schema, conversation_history)
            else:
                print("[Interviewer] Controller in negotiate_curriculum mode - returning clarifying question")
                # Return regular response - a clarifying question about curriculum modifications
                return self.generate_next_question(schema, conversation_history)

        if is_proposing_curriculum:
            # Use JSON mode for curriculum proposals - much more reliable than text parsing
            return self._generate_curriculum_proposal_json(schema, conversation_history)

        # Regular conversation - use text mode
        return self.generate_next_question(schema, conversation_history)

    def generate_response_stream(
        self,
        user_message: str,
        schema: DiscoverySchema,
        conversation_history: List[Dict]
    ) -> Generator[Union[str, Dict], None, None]:
        """
        Streaming version of generate_response.

        For regular conversation, yields text chunks as they stream from the LLM.
        For curriculum proposals (structured JSON), yields a single dict at the end
        since those can't be meaningfully streamed.

        Yields:
            str chunks for regular conversation, or a single Dict for curriculum proposals
        """
        is_proposing_curriculum = schema.controller.conversation_mode == "propose_tasks"
        is_negotiating_curriculum = schema.controller.conversation_mode == "negotiate_curriculum"

        is_manual_generation = (
            is_proposing_curriculum and
            schema.controller.next_action == "propose_task_curriculum"
        )

        if is_proposing_curriculum and not schema.task_curriculum.proposed and not is_manual_generation:
            is_proposing_curriculum = False

        # Curriculum proposals need structured JSON — can't stream those
        if is_negotiating_curriculum:
            if schema.controller and schema.controller.next_action == "propose_task_curriculum":
                yield self._generate_curriculum_proposal_json(schema, conversation_history)
                return
            else:
                # Clarifying question — stream it
                yield from self.generate_next_question_stream(schema, conversation_history)
                return

        if is_proposing_curriculum:
            yield self._generate_curriculum_proposal_json(schema, conversation_history)
            return

        # Regular conversation — stream it
        yield from self.generate_next_question_stream(schema, conversation_history)

    def _generate_curriculum_proposal_json(
        self,
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]]
    ) -> Dict:
        """
        Generate curriculum proposal using JSON mode for reliable structured output.

        Args:
            schema: Current discovery schema
            conversation_history: Full conversation history

        Returns:
            Dict with type, text, tasks, and goal
        """
        print("[Interviewer] Generating curriculum proposal using JSON mode")
        
        # Determine phase
        phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"
        
        # Load propose_tasks prompt
        formatted_prompt, dropped = assemble_prompt(
            step_name="propose_tasks",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            schema_state=schema,
            conversation_history=conversation_history,
            task="interviewer",
            phase=phase,
        )
        
        # Check if this is a modification request (curriculum already proposed)
        is_modification = schema.task_curriculum.proposed and not schema.task_curriculum.accepted
        modification_note = ""
        if is_modification:
            # Get the last user message which should contain the modification request
            last_user_msg = next((m for m in reversed(conversation_history) if m.get("role") == "user"), None)
            if last_user_msg:
                modification_note = f"\n\nIMPORTANT: The user has requested modifications to the curriculum. Their request: '{last_user_msg.get('content', '')}'\n\nYou MUST incorporate this feedback. If they asked to skip basics, remove foundational tasks. If they want practical focus, prioritize hands-on tasks. Design the curriculum to match what they asked for."
        
        # Add JSON schema instruction
        json_schema_instruction = f"""
You MUST respond with valid JSON in this exact format:
{{
  "text": "The natural language curriculum proposal message to show the user",
  "tasks": [
    {{
      "id": 1,
      "topic": "Task name",
      "justification": "Why this task matters for the user",
      "prerequisites": [],
      "status": "available"
    }},
    {{
      "id": 2,
      "topic": "Next task name",
      "justification": "Why this task matters",
      "prerequisites": [1],
      "status": "locked"
    }}
    // ... 8-12 tasks total
  ]
}}

Generate 8-12 tasks. The first task should have status "available" and prerequisites []. 
Subsequent tasks should have prerequisites [previous_task_id] and status "locked".
{modification_note}
"""
        
        messages = [
            {"role": "system", "content": formatted_prompt},
            {"role": "user", "content": json_schema_instruction}
        ]
        messages.extend(self._select_history_for_question(conversation_history))
        
        # Use JSON mode
        try:
            response = self.llm.chat_with_json(
                messages=messages,
                model=get_model_name("interviewer", default="claude-sonnet-4-20250514"),
                temperature=0.7,
                max_tokens=2000,
                json_top_level="object"
            )
            
            # Validate response structure
            if not isinstance(response, dict):
                raise ValueError(f"Expected dict, got {type(response)}")
            
            if "tasks" not in response:
                raise ValueError("Response missing 'tasks' field")
            
            if "text" not in response:
                # Generate text from tasks if missing
                tasks = response.get("tasks", [])
                goal = schema.interview_state.user_goal or "your learning goal"
                response["text"] = f"Based on your goal '{goal}' and what I've learned about your background, here's a complete learning path I've designed for you:\n\n" + "\n".join([f"{t.get('id', i+1)}. {t.get('topic', 'Task')}\n   Why for you: {t.get('justification', '')}" for i, t in enumerate(tasks)]) + "\n\nThis is my best guess at the complete journey. We can adjust this as we go based on what works for you."
            
            # Validate and fix tasks
            tasks = response.get("tasks", [])
            if len(tasks) < 8:
                print(f"[Interviewer] WARNING: Only {len(tasks)} tasks, expanding to 8...")
                goal = schema.interview_state.user_goal or "your learning goal"
                while len(tasks) < 8:
                    next_id = len(tasks) + 1
                    tasks.append({
                        "id": next_id,
                        "topic": f"Additional learning step {next_id}",
                        "justification": f"Essential component {next_id} for achieving {goal}",
                        "prerequisites": [next_id - 1] if next_id > 1 else [],
                        "status": "locked"
                    })
                response["tasks"] = tasks
            
            # Ensure first task is available
            if tasks and tasks[0].get("status") != "available":
                tasks[0]["status"] = "available"
                tasks[0]["prerequisites"] = []
            
            # Ensure prerequisites are correct
            for i, task in enumerate(tasks):
                if i > 0 and task.get("id", i+1) > 1:
                    task["prerequisites"] = [tasks[i-1].get("id", i)]
                    task["status"] = "locked"
            
            print(f"[Interviewer] Generated curriculum with {len(tasks)} tasks via JSON mode")
            
            return {
                "type": "curriculum_proposal",
                "text": response["text"],
                "tasks": tasks,
                "goal": schema.interview_state.user_goal
            }
            
        except Exception as e:
            print(f"[Interviewer] ERROR: JSON mode failed: {e}")
            print("[Interviewer] Falling back to text mode with synthetic tasks")
            # Fallback: create synthetic curriculum
            goal = schema.interview_state.user_goal or "your learning goal"
            tasks = [
                {
                    "id": i + 1,
                    "topic": f"Step {i+1} toward {goal}",
                    "justification": f"Essential component {i+1} for achieving your goal",
                    "prerequisites": [i] if i > 0 else [],
                    "status": "available" if i == 0 else "locked"
                }
                for i in range(12)
            ]
            text = f"Based on your goal '{goal}' and what I've learned about your background, here's a complete learning path I've designed for you:\n\n" + "\n".join([f"{t['id']}. {t['topic']}\n   Why for you: {t['justification']}" for t in tasks]) + "\n\nThis is my best guess at the complete journey. We can adjust this as we go based on what works for you."
            
            return {
                "type": "curriculum_proposal",
                "text": text,
                "tasks": tasks,
                "goal": goal
            }

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
