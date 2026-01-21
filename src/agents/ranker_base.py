"""Base class for ranker agents with shared functionality."""
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.llm_client import LLMClient
from src.config import get_model_name, get_conversation_max_turns
from src.schema.full_schema import (
    DiscoverySchema,
    UserProfile,
    ConversationalTheme,
    TeachingCandidate,
    Controller,
    TeachingRecommendation
)
from src.prompt_loader import PromptLoader


class RankerAgentBase(ABC):
    """
    Base class for ranker agents that analyze conversation and update schema.

    This abstract base class provides shared functionality for:
    - Parallel LLM orchestration
    - Profile and theme updates
    - Conversation formatting

    Subclasses must implement:
    - _get_gatable_dimensions(): Dimension priority logic
    - _check_teaching_readiness(): Readiness criteria and thresholds

    Subclasses may override:
    - _update_teaching_candidates(): For goal-aware filtering
    - _generate_controller(): For specialized prompts
    - _should_skip_profile_update(): For different optimization thresholds
    - _should_skip_themes_update(): For different optimization thresholds
    """

    def __init__(self, llm_client: LLMClient, model_config: Optional[str] = None):
        """
        Initialize ranker agent.

        Args:
            llm_client: LLM client for making API calls
            model_config: Optional model override (e.g., "cerebras:llama-3.3-70b")
        """
        self.llm = llm_client
        self.prompt_loader = PromptLoader()
        self.model_override = model_config  # Store for use in all model calls

    def get_prompt_variant(self) -> str:
        """
        Return the prompt variant for this ranker type.

        Returns:
            "goal_discovery" for GoalDiscoveryRanker, "teaching_discovery" for TeachingCandidateRanker

        Note: Subclasses must override this method.
        """
        raise NotImplementedError("Subclasses must implement get_prompt_variant()")

    @abstractmethod
    def update_schema(
        self,
        current_schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> DiscoverySchema:
        """
        Analyze conversation and update the schema.

        ABSTRACT METHOD - must be implemented by subclasses.

        Subclasses should implement phased execution:
        - Phase 1: branch_condition, user_profile, conversational_themes (parallel)
        - Phase 2: goal_candidates or teaching_candidates (sequential - needs fresh themes)
        - Phase 3: controller + readiness (parallel)

        Args:
            current_schema: Current discovery schema
            conversation_history: Full conversation history
            user_message: Latest user message

        Returns:
            Updated discovery schema
        """
        pass

    def _not_ready_recommendation(self) -> Dict[str, Any]:
        """Fast-path default for 'not ready' teaching recommendation."""
        return {
            "ready": False,
            "target_topic_id": None,
            "target_topic": None,
            "focus_question": None,
            "angle": None,
            "difficulty_calibration": None,
            "format": None,
            "pacing": None,
            "first_move": None
        }

    def _should_skip_profile_update(self, schema: DiscoverySchema) -> bool:
        """
        Determine if we can skip the profile update LLM call.

        Default implementation. Subclasses may override for different thresholds.

        Skip when:
        - Average confidence across key dimensions is high (>0.7)
        - We're past turn 4 (enough data collected)

        Returns:
            True if profile update can be skipped
        """
        # Never skip on early turns - we need to build the profile
        if schema.interview_state.turns_elapsed < 4:
            return False

        try:
            confidences = [
                schema.user_profile.curiosity_type.confidence,
                schema.user_profile.uncertainty_tolerance.confidence,
                schema.user_profile.interest_phase_default.confidence,
                schema.user_profile.pacing_preference.confidence,
            ]
            avg_confidence = sum(confidences) / len(confidences)

            # Skip if we're confident enough
            return avg_confidence >= 0.7
        except Exception:
            return False

    def _should_skip_themes_update(self, schema: DiscoverySchema) -> bool:
        """
        Determine if we can skip the themes update LLM call.

        Default implementation. Subclasses may override for different thresholds.

        Skip when:
        - We have at least one teaching candidate with high readiness
        - We're past turn 5 and themes are stable

        Returns:
            True if themes update can be skipped
        """
        # Never skip on early turns
        if schema.interview_state.turns_elapsed < 5:
            return False

        # Check if we have a strong teaching candidate
        for candidate in schema.teaching_candidates:
            if candidate.readiness_score >= 0.7:
                # We have a strong candidate, themes are less important now
                return True

        return False

    @abstractmethod
    def _get_gatable_dimensions(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Determine which dimensions are still uncertain (can be asked about)
        vs. which are known (should not be re-asked).

        ABSTRACT METHOD - must be implemented by subclasses.

        Different ranker types prioritize dimensions differently:
        - GoalDiscoveryRanker (Phase 1): High urgency for curiosity_type, entry_mode, motivation
        - TeachingCandidateRanker (Phase 2): High urgency for uncertainty_tolerance, pacing

        Returns dict with:
          - gatable: list of dimension names that need more signal
          - exhausted: list of dimension names that are confident enough
          - urgency_multipliers: dict of dimension -> float urgency boost
        """
        pass

    def _classify_branch_condition(
        self,
        user_message: str,
        history: List[Dict[str, str]]
    ) -> str:
        """
        Use LLM to classify what type of response the user gave.

        Returns: topic_mentioned | personal_shared | deflection |
                 preference_signal | question_asked | unclear
        """
        classification_prompt = f"""Classify the user's most recent response into ONE of these categories:

- topic_mentioned: User named a specific domain, field, concept, question, or phenomenon they want to learn about
- personal_shared: User shared something about themselves, their situation, feelings, or life context
- deflection: User avoided the question, said "I don't know," or gave a non-answer
- preference_signal: User expressed a preference about how they learn or what they value
- question_asked: User asked a question back to you
- unclear: None of the above clearly applies

Recent conversation:
{self._format_conversation(history[-3:] if len(history) > 3 else history)}

User's most recent response: "{user_message}"

Respond with ONLY the category name, nothing else."""

        try:
            # Use model_override if provided, otherwise use config/default
            model = self.model_override if self.model_override else get_model_name("ranker", "branch_classifier", default="claude-3-5-haiku-20241022")

            response = self.llm.chat(
                messages=[{"role": "user", "content": classification_prompt}],
                model=model,
                temperature=0.3,
                max_tokens=50
            ).strip().lower()

            # Validate response
            valid_conditions = [
                "topic_mentioned", "personal_shared", "deflection",
                "preference_signal", "question_asked", "unclear"
            ]

            return response if response in valid_conditions else "unclear"

        except Exception as e:
            print(f"[ERROR] Error classifying branch condition: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Branch classification failed: {str(e)}")

    def _update_user_profile(
        self,
        schema: DiscoverySchema,
        history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Update user profile dimensions based on conversation.

        Returns:
            Updated profile dictionary
        """
        try:
            prompt_template = self.prompt_loader.load_ranker_prompt("update_user_profile")

            # Format with current schema context
            formatted_prompt = prompt_template.format(
                current_profile=schema.user_profile.model_dump(),
                conversation=self._format_conversation(history)
            )

            messages = [{"role": "user", "content": formatted_prompt}]

            # Use model_override if provided, otherwise use config/default
            model = self.model_override if self.model_override else get_model_name("ranker", "profile", default="claude-sonnet-4-20250514")
            print(f"[DEBUG] Ranker profile update using model: {model} (override={self.model_override})")

            response = self.llm.chat_with_json(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=2000,
                json_top_level="object",
            )

            return response

        except Exception as e:
            print(f"[ERROR] Error updating user profile: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Profile update failed: {str(e)}")

    def _update_conversational_themes(
        self,
        schema: DiscoverySchema,
        history: List[Dict[str, str]],
        current_turn: int
    ) -> List[Dict[str, Any]]:
        """
        Update conversational themes based on conversation.

        Uses phase-specific prompts:
        - Phase 1 (Goal Discovery): Breadth-focused, captures all signals
        - Phase 2 (Teaching Discovery): Depth-focused, prioritizes goal-relevant themes

        Returns:
            List of updated conversational theme dictionaries
        """
        try:
            # Debug: show current themes being passed in
            print(f"[DEBUG] Current themes being passed to ranker: {len(schema.conversational_themes)}")
            for theme in schema.conversational_themes:
                print(f"  - ID {theme.id}: {theme.theme_seed} (type: {theme.theme_type})")

            # Determine phase and load phase-specific prompt
            phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"
            prompt_template = self.prompt_loader.load_ranker_prompt(
                "update_conversational_themes_delta",
                variant=phase
            )

            # Format with current schema context
            # Only pass recent history (last 4 turns) to enforce incremental updates and reduce noise
            recent_history = history[-8:] if len(history) > 8 else history # 4 turns = 8 messages (user+assistant)

            # Phase-specific formatting
            if phase == "teaching_discovery":
                # Phase 2: Include user_goal and teaching_candidates for context
                formatted_prompt = prompt_template.format(
                    user_goal=schema.interview_state.user_goal or "",
                    conversational_themes=[t.model_dump() for t in schema.conversational_themes],
                    teaching_candidates=[t.model_dump() for t in schema.teaching_candidates],
                    conversation=self._format_conversation(recent_history)
                )
            else:
                # Phase 1: Just themes and conversation
                formatted_prompt = prompt_template.format(
                    conversational_themes=[t.model_dump() for t in schema.conversational_themes],
                    conversation=self._format_conversation(recent_history)
                )

            # Debug: show snippet of conversation being analyzed
            conv_snippet = self._format_conversation(history[-2:] if len(history) > 2 else history)
            print(f"[DEBUG] Themes delta analyzing: {conv_snippet[:150]}...")

            messages = [{"role": "user", "content": formatted_prompt}]

            # Use model_override if provided, otherwise use config/default
            model = self.model_override if self.model_override else get_model_name("ranker", "themes", default="claude-sonnet-4-20250514")

            delta = self.llm.chat_with_json(
                messages=messages,
                model=model,
                temperature=0.1,  # Lower temperature for more literal extraction of concrete topics
                max_tokens=1500,  # Reduced from 3000 for faster generation
                json_top_level="object",
            )

            # Parse delta format: {"upserts": [...], "abandon_ids": [...]}
            upserts = []
            abandon_ids = []
            if isinstance(delta, dict):
                upserts = delta.get("upserts", []) or []
                abandon_ids = delta.get("abandon_ids", []) or []
            elif isinstance(delta, list):
                # Back-compat: treat list as upserts
                upserts = delta

            if not isinstance(upserts, list):
                upserts = []
            if not isinstance(abandon_ids, list):
                abandon_ids = []

            # Merge upserts into existing themes.
            existing_by_id: Dict[int, Dict[str, Any]] = {t.id: t.model_dump() for t in schema.conversational_themes}
            next_id = (max(existing_by_id.keys()) + 1) if existing_by_id else 1

            # Apply abandonments
            for tid in abandon_ids:
                try:
                    tid_int = int(tid)
                    if tid_int in existing_by_id:
                        del existing_by_id[tid_int]
                except Exception:
                    continue

            for t in upserts:
                if not isinstance(t, dict):
                    continue
                # Drop None keys to allow defaults to apply later
                t = {k: v for k, v in t.items() if v is not None}

                tid = t.get("id")
                if tid is None:
                    # New theme: assign id
                    t["id"] = next_id
                    existing_by_id[next_id] = t
                    next_id += 1
                    continue

                try:
                    tid_int = int(tid)
                except Exception:
                    # If id is malformed, treat as new
                    t["id"] = next_id
                    existing_by_id[next_id] = t
                    next_id += 1
                    continue

                if tid_int in existing_by_id:
                    merged = dict(existing_by_id[tid_int])
                    merged.update(t)  # patch semantics
                    existing_by_id[tid_int] = merged
                else:
                    # Unknown id: treat as new with that id if safe, else assign next
                    if tid_int >= next_id:
                        existing_by_id[tid_int] = t
                        next_id = tid_int + 1
                    else:
                        t["id"] = next_id
                        existing_by_id[next_id] = t
                        next_id += 1

            response = [existing_by_id[k] for k in sorted(existing_by_id.keys())]

            # Debug: show what ranker returned
            print(f"[DEBUG] Ranker returned {len(response)} themes:")
            for theme in response:
                print(f"  - ID {theme.get('id')}: {theme.get('theme_seed')} (type: {theme.get('theme_type')})")

            return response

        except Exception as e:
            print(f"[ERROR] Error updating conversational themes: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Themes update failed: {str(e)}")

    def _update_goal_candidates(
        self,
        schema: DiscoverySchema,
        history: List[Dict[str, str]],
        current_turn: int
    ) -> List[Dict[str, Any]]:
        """
        Update goal candidates based on conversation (exploratory phase 1).

        Goal candidates are high-level multi-lesson learning outcomes that:
        - Are outcome-oriented (e.g., "Become conversational in Spanish")
        - Require multiple lessons to accomplish
        - Are break-apartable into teachable sub-goals

        Returns:
            List of updated goal candidate dictionaries
        """
        try:
            # Debug: show current goal candidates
            print(f"[GOAL DISCOVERY] Current goal candidates: {len(schema.goal_candidates)}")
            for cand in schema.goal_candidates:
                print(f"  - ID {cand.id}: {cand.goal} (readiness: {cand.readiness_score:.2f})")

            # Get already-accepted goals to avoid proposing similar ones
            accepted_goal_ids = set(schema.interview_state.accepted_goal_ids)
            accepted_goals = [g.goal for g in schema.goal_candidates if g.id in accepted_goal_ids]
            if accepted_goals:
                print(f"[GOAL DISCOVERY] Already accepted goals: {accepted_goals}")

            prompt_template = self.prompt_loader.load_ranker_prompt("update_goal_candidates", variant=self.get_prompt_variant())

            # Limit conversation history to last 12 messages (6 turns) for faster processing
            # Goal candidates don't need full history - recent context is sufficient
            limited_history = history[-12:] if len(history) > 12 else history
            print(f"[TIMING] Using {len(limited_history)}/{len(history)} messages for goal_candidates (optimized)")

            # Format with current schema context
            formatted_prompt = prompt_template.format(
                goal_candidates=[g.model_dump() for g in schema.goal_candidates],
                conversational_themes=[t.model_dump() for t in schema.conversational_themes],
                conversation=self._format_conversation(limited_history),
                accepted_goals=accepted_goals if accepted_goals else "None yet"
            )

            messages = [{"role": "user", "content": formatted_prompt}]

            # Use model_override if provided, otherwise use config/default
            model_name = self.model_override if self.model_override else get_model_name("ranker", "goal_candidates", default="openai:gpt-4o")

            print(f"[TIMING] Calling LLM for goal_candidates with model: {model_name}")
            llm_start = time.time()
            parsed = self.llm.chat_with_json(
                messages=messages,
                model=model_name,
                temperature=0.2,
                json_top_level="any"
            )
            print(f"[TIMING] goal_candidates LLM response received in {time.time() - llm_start:.2f}s")

            # Handle both array and object with array
            if isinstance(parsed, list):
                return parsed
            elif "goal_candidates" in parsed:
                return parsed["goal_candidates"]
            elif isinstance(parsed, dict):
                # Try to find array in dict values
                for value in parsed.values():
                    if isinstance(value, list):
                        return value

            print(f"[WARNING] Unexpected goal candidates format: {type(parsed)}")
            return []

        except Exception as e:
            print(f"[ERROR] Error updating goal candidates: {e}")
            import traceback
            traceback.print_exc()
            return [g.model_dump() for g in schema.goal_candidates]  # Return current state

    def _update_teaching_candidates(
        self,
        schema: DiscoverySchema,
        history: List[Dict[str, str]],
        current_turn: int
    ) -> List[Dict[str, Any]]:
        """
        Update teaching candidates based on conversation (phase 2).

        Default implementation. Subclasses may override for goal-aware filtering.

        ONLY creates teaching candidates for concrete conceptual topics that pass:
        - Concreteness test (can find a book chapter about it)
        - Scope test (can be taught in 5-15 minutes)
        - Question test (has specific gap/question)

        Returns:
            List of updated teaching candidate dictionaries
        """
        try:
            # Debug: show current teaching candidates
            print(f"[DEBUG] Current teaching candidates: {len(schema.teaching_candidates)}")
            for cand in schema.teaching_candidates:
                print(f"  - ID {cand.id}: {cand.topic}")

            prompt_template = self.prompt_loader.load_ranker_prompt("update_teaching_candidates", variant=self.get_prompt_variant())

            # Format with current schema context
            # Include task_curriculum if it exists (for modification detection)
            task_curriculum_str = "None (not yet proposed)"
            if schema.task_curriculum and (schema.task_curriculum.proposed or len(schema.task_curriculum.tasks) > 0):
                import json
                task_curriculum_str = json.dumps(schema.task_curriculum.model_dump(), indent=2)
            
            formatted_prompt = prompt_template.format(
                teaching_candidates=[t.model_dump() for t in schema.teaching_candidates],
                conversational_themes=[t.model_dump() for t in schema.conversational_themes],
                task_curriculum=task_curriculum_str,
                conversation=self._format_conversation(history),
                user_goal=schema.interview_state.user_goal or "Not yet identified"
            )

            messages = [{"role": "user", "content": formatted_prompt}]

            # Use model_override if provided, otherwise use config/default
            model = self.model_override if self.model_override else get_model_name("ranker", "teaching_candidates", default="claude-sonnet-4-20250514")

            response = self.llm.chat_with_json(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=1500,  # Reduced from 3000 for faster generation
                json_top_level="array",
            )

            # Handle response - LLM may return either array or object with teaching_candidates + task_curriculum
            task_curriculum_data = None
            if isinstance(response, dict):
                # Check if LLM returned nested format like {'teaching_candidates': [...], 'task_curriculum': {...}}
                if 'task_curriculum' in response:
                    task_curriculum_data = response['task_curriculum']
                    print(f"[DEBUG] LLM returned task_curriculum: proposed={task_curriculum_data.get('proposed')}, tasks={len(task_curriculum_data.get('tasks', []))}")
                if 'teaching_candidates' in response:
                    response = response['teaching_candidates']
                else:
                    # If ranker returned a single teaching candidate, wrap it
                    response = [response]
            if not isinstance(response, list):
                response = []
            
            # PHASE 3: Update task_curriculum with state preservation
            # CRITICAL: Don't overwrite curriculum state once it's been set by orchestrator
            if task_curriculum_data and task_curriculum_data.get('tasks'):
                from src.schema.full_schema import ProposedTask, TaskCurriculum

                # If curriculum is already accepted, DON'T overwrite it
                if schema.task_curriculum.accepted:
                    print("[Ranker] Curriculum already accepted, preserving state")
                    # Don't update task_curriculum at all

                # If curriculum is proposed but not accepted, preserve proposal state
                elif schema.task_curriculum.proposed and not schema.task_curriculum.accepted:
                    print("[Ranker] Curriculum proposed, preserving proposal state")
                    # Ranker CAN update tasks during modification flow, but must preserve proposed=True
                    # This allows ranker to handle curriculum modifications
                    new_tasks = [ProposedTask(**t) for t in task_curriculum_data.get('tasks', [])]
                    modification_history = task_curriculum_data.get('modification_history', schema.task_curriculum.modification_history)

                    schema.task_curriculum = TaskCurriculum(
                        proposed=True,  # Preserve proposed state!
                        accepted=False,  # Keep accepting state
                        tasks=new_tasks,
                        modification_history=modification_history
                    )
                    print(f"[Ranker] Updated curriculum tasks ({len(new_tasks)} tasks) while preserving proposed=True")

                # Only update task_curriculum if it's NOT proposed yet
                else:
                    # Ranker can populate task_curriculum with candidates, but NOT set proposed=True
                    # That's now the interviewer's job
                    new_tasks = [ProposedTask(**t) for t in task_curriculum_data.get('tasks', [])]
                    schema.task_curriculum = TaskCurriculum(
                        proposed=False,  # DON'T set proposed=True - interviewer controls that
                        accepted=False,
                        tasks=new_tasks,
                        modification_history=[]
                    )
                    print(f"[Ranker] Populated task_curriculum with {len(new_tasks)} candidate tasks (proposed=False)")

            sanitized: List[Dict[str, Any]] = []
            for c in response:
                if isinstance(c, dict):
                    sanitized.append({k: v for k, v in c.items() if v is not None})
            response = sanitized

            # Debug: show what ranker returned
            print(f"[DEBUG] Ranker returned {len(response)} teaching candidates:")
            for cand in response:
                print(f"  - ID {cand.get('id')}: {cand.get('topic')}")

            # Validation: ensure no existing teaching candidates were dropped
            existing_ids = {t.id for t in schema.teaching_candidates}
            returned_ids = {t.get('id') for t in response}
            dropped_ids = existing_ids - returned_ids

            if dropped_ids:
                print(f"[WARNING] Ranker dropped {len(dropped_ids)} teaching candidates (IDs: {dropped_ids})")
                print("[WARNING] Merging dropped teaching candidates back into response...")

                # Add back the dropped teaching candidates
                for cand in schema.teaching_candidates:
                    if cand.id in dropped_ids:
                        print(f"  - Restoring teaching candidate ID {cand.id}: {cand.topic}")
                        response.append(cand.model_dump())

            return response

        except Exception as e:
            print(f"[ERROR] Error updating teaching candidates: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Teaching candidates update failed: {str(e)}")

    def _generate_controller(
        self,
        schema: DiscoverySchema,
        branch_condition: str,
        user_message: str = ""
    ) -> Dict[str, Any]:
        """
        Generate next question and controller state.

        Default implementation. Subclasses may override for specialized prompts.

        Returns:
            Controller dictionary
        """
        try:
            prompt_template = self.prompt_loader.load_ranker_prompt("generate_controller", variant=self.get_prompt_variant())

            # Get dimension gating info to pass to the prompt
            dimension_gating = self._get_gatable_dimensions(schema)

            # Debug output for dimension gating
            print(f"[DIMENSION GATING] Gatable: {dimension_gating['gatable']}")
            print(f"[DIMENSION GATING] Exhausted: {dimension_gating['exhausted']}")
            print(f"[PROFILE CONFIDENCE] curiosity: {schema.user_profile.curiosity_type.confidence:.2f}, entry: {max(schema.user_profile.entry_mode.people, schema.user_profile.entry_mode.problems, schema.user_profile.entry_mode.ideas):.2f}, uncertainty: {schema.user_profile.uncertainty_tolerance.confidence:.2f}")

            # Get question history to avoid repetition
            recent_intents = schema.interview_state.recent_question_intents if schema.interview_state else []
            recent_summaries = schema.interview_state.recent_question_summaries if schema.interview_state else []

            # Get goal information if provided
            user_goal = schema.interview_state.user_goal if schema.interview_state and schema.interview_state.goal_provided else None
            goal_provided = schema.interview_state.goal_provided if schema.interview_state else False

            formatted_prompt = prompt_template.format(
                schema=self._schema_dump_for_llm(schema),
                branch_condition=branch_condition,
                gatable_dimensions=dimension_gating["gatable"],
                exhausted_dimensions=dimension_gating["exhausted"],
                dimension_urgencies=dimension_gating["urgency_multipliers"],
                recent_question_intents=recent_intents,
                recent_question_summaries=recent_summaries,
                user_goal=user_goal or "None",
                goal_provided=goal_provided,
                user_message=user_message or ""
            )

            # PRE-LLM: Pattern matching for common ambiguity signals
            ambiguity_patterns = [
                "both", "either", "all of", "all of them", "everything",
                "i don't know", "idk", "not sure", "you choose", "you decide",
                "whatever", "doesn't matter", "any", "whichever"
            ]

            user_message_lower = user_message.lower() if user_message else ""
            detected_ambiguity = any(pattern in user_message_lower for pattern in ambiguity_patterns)

            # If ambiguity detected, force grounded_offer or propose_tasks mode
            if detected_ambiguity:
                print(f"[CONTROLLER] Ambiguity detected in user message: '{user_message[:50] if user_message else ''}...'")
                # Check assessment confidence to decide next move
                assessment_confidence = getattr(schema.prior_knowledge_assessment, 'confidence', 0.0) if hasattr(schema, 'prior_knowledge_assessment') else 0.0
                turns_elapsed = schema.interview_state.turns_elapsed if schema.interview_state else 0

                if assessment_confidence >= 0.5 or turns_elapsed >= 8:
                    # We have enough info - propose concrete curriculum
                    force_next_action = "propose_task_curriculum"
                    force_conversation_mode = "propose_tasks"
                    force_focus_instruction = "User gave ambiguous answer ('both'/'you choose'). We have enough assessment data. Propose a concrete learning path with 8-12 tasks based on what we've learned about their level."
                else:
                    # Still assessing - offer concrete starting point
                    force_next_action = "provide_scaffolding"
                    force_conversation_mode = "grounded_offer"
                    force_focus_instruction = "User gave ambiguous answer ('both'/'you choose'). Offer a concrete starting point with a specific recommendation. Do not ask them to choose again - make a recommendation and explain why."

                # Skip LLM call and return deterministic controller
                return {
                    "next_action": force_next_action,
                    "question_intent": "present_learning_path" if force_next_action == "propose_task_curriculum" else "reduce_cost",
                    "conversation_mode": force_conversation_mode,
                    "target_ambiguity": None,
                    "focus_instruction": force_focus_instruction,
                    "branch_condition": "deflection",
                    "fallback_questions": []
                }

            messages = [{"role": "user", "content": formatted_prompt}]

            # Use model_override if provided from UI, otherwise use config/default
            model = self.model_override if self.model_override else get_model_name("ranker", "controller", default="claude-sonnet-4-20250514")
            print(f"[DEBUG] Controller using model: {model} (override={self.model_override})")

            response = self.llm.chat_with_json(
                messages=messages,
                model=model,
                temperature=0.5,
                max_tokens=1000,
                json_top_level="object",
            )

            # POST-PROCESSING: Enforce forward progress

            proposed_intent = response.get("question_intent", "")
            proposed_action = response.get("next_action", "")

            # 1. Intent variety check with ESCALATION
            if proposed_intent and recent_intents:
                # Count how many times this intent was used recently
                intent_count = recent_intents.count(proposed_intent)
                if intent_count >= 2:
                    print(f"[CONTROLLER] WARNING: Intent '{proposed_intent}' used {intent_count}+ times, forcing escalation")

                    # Instead of just varying intent, ESCALATE to concrete offer
                    assessment_confidence = getattr(schema.prior_knowledge_assessment, 'confidence', 0.0) if hasattr(schema, 'prior_knowledge_assessment') else 0.0
                    turns_elapsed = schema.interview_state.turns_elapsed if schema.interview_state else 0

                    if assessment_confidence >= 0.4 or turns_elapsed >= 6:
                        # Enough probing - time to propose concrete path
                        response["next_action"] = "propose_task_curriculum"
                        response["question_intent"] = "present_learning_path"
                        response["conversation_mode"] = "propose_tasks"
                        response["focus_instruction"] = f"[Escalated from repeated {proposed_intent}] We've probed {intent_count} times. Time to move forward. Propose a concrete learning path with 8-12 tasks based on current understanding."
                        print(f"[CONTROLLER] ESCALATED to propose_task_curriculum")
                    else:
                        # Still early - force grounded_offer with concrete recommendation
                        response["next_action"] = "provide_scaffolding"
                        response["question_intent"] = "reduce_cost"
                        response["conversation_mode"] = "grounded_offer"
                        response["focus_instruction"] = f"[Escalated from repeated {proposed_intent}] We've asked {intent_count} similar questions. Offer a concrete starting point with a specific recommendation instead of asking them to choose."
                        print(f"[CONTROLLER] ESCALATED to grounded_offer with recommendation")

            # 2. Check if we're stuck on same topic (semantic similarity in recent questions)
            if len(recent_summaries) >= 3:
                # Simple heuristic: if last 3 questions share common keywords, we're stuck
                last_three = recent_summaries[-3:]
                # Extract key terms (simple approach - can be enhanced)
                all_words = ' '.join(last_three).lower()

                # Common stuck patterns
                stuck_keywords = [
                    ("theory", "practice", "application"),  # Theory/practice dimension
                    ("historical", "practical", "context"),  # Context dimension
                    ("concepts", "examples", "applications")  # Concrete/abstract dimension
                ]

                for keyword_group in stuck_keywords:
                    matches = sum(1 for word in keyword_group if word in all_words)
                    if matches >= 2:
                        print(f"[CONTROLLER] Stuck pattern detected: {keyword_group} appears in last 3 questions")

                        # Force recommendation instead of another question
                        response["next_action"] = "provide_scaffolding"
                        response["question_intent"] = "reduce_cost"
                        response["conversation_mode"] = "grounded_offer"
                        response["focus_instruction"] = f"[Escalated - stuck pattern] We've circled this topic 3+ times. Make a concrete recommendation for where to start. Don't ask them to choose - tell them what we'll do and why it's a good fit."
                        print(f"[CONTROLLER] ESCALATED due to stuck pattern")
                        break

            return response

        except Exception as e:
            print(f"[ERROR] Error generating controller: {e}")
            import traceback
            traceback.print_exc()
            # Don't return a fallback - raise the error so it's shown to the user
            raise Exception(f"Controller generation failed: {str(e)}")

    @abstractmethod
    def _check_teaching_readiness(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Determine if ready to transition to teaching phase.

        ABSTRACT METHOD - must be implemented by subclasses.

        Different ranker types have different readiness criteria:
        - GoalDiscoveryRanker (Phase 1): Checks goal readiness, not teaching readiness
        - TeachingCandidateRanker (Phase 2): 0.65 threshold for teaching candidates

        Returns:
            TeachingRecommendation dictionary
        """
        pass

    def _format_conversation(self, history: List[Dict[str, str]]) -> str:
        """
        Format conversation history as readable text.

        Args:
            history: List of message dictionaries

        Returns:
            Formatted conversation string
        """
        # Default trim to keep prompts fast and bounded as the conversation grows.
        # Callers that need a smaller window can still slice history before passing it in.
        max_messages = 12
        max_chars = 8000

        window = history[-max_messages:] if len(history) > max_messages else history

        lines: List[str] = []
        for msg in window:
            role = msg['role'].capitalize()
            lines.append(f"{role}: {msg['content']}")

        # Enforce a rough character limit by dropping oldest lines first.
        while lines and sum(len(l) + 1 for l in lines) > max_chars:
            lines.pop(0)

        return "\n".join(lines)

    def _schema_dump_for_llm(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Reduce schema payload size for LLM prompts.

        The controller/readiness prompts don't need the full unbounded schema;
        sending only the most salient items saves tokens and latency.

        Phase is auto-detected from schema.interview_state.goal_identified:
        - goal_discovery: Include goal_candidates, no teaching_candidates
        - teaching_discovery: Include teaching_candidates, expose user_goal
        """
        try:
            # Determine phase from goal_identified
            phase = "teaching_discovery" if schema.interview_state.goal_identified else "goal_discovery"

            top_themes = sorted(
                schema.conversational_themes,
                key=lambda t: t.readiness_score,
                reverse=True
            )[:12]

            max_turns = max(4, get_conversation_max_turns(default=8))
            turns_elapsed = schema.interview_state.turns_elapsed
            urgency = min(1.0, max(0.0, turns_elapsed / float(max_turns - 1)))
            has_concrete_theme = any(t.theme_type == "concrete_topic" for t in schema.conversational_themes)
            if not has_concrete_theme and turns_elapsed >= 2:
                urgency = min(1.0, urgency + 0.2)

            # Base schema
            result = {
                "session_id": schema.session_id,
                "derived": {
                    "turns_elapsed": turns_elapsed,
                    "max_turns": max_turns,
                    "urgency": urgency,
                    "phase": phase,
                },
                "user_profile": schema.user_profile.model_dump(),
                "interview_state": schema.interview_state.model_dump(),
                "conversational_themes": [t.model_dump() for t in top_themes],
                "controller": schema.controller.model_dump() if schema.controller else None,
                "teaching_recommendation": schema.teaching_recommendation.model_dump() if schema.teaching_recommendation else None,
            }

            # Phase-specific candidate inclusion
            if phase == "goal_discovery":
                # Goal Discovery: Include goal_candidates, minimal teaching_candidates
                top_goals = sorted(
                    schema.goal_candidates,
                    key=lambda c: c.readiness_score,
                    reverse=True
                )[:8]
                result["goal_candidates"] = [g.model_dump() for g in top_goals]
                result["teaching_candidates"] = []  # Not relevant in Phase 1
            else:
                # Teaching Discovery: Include teaching_candidates, reference user_goal
                top_teaching = sorted(
                    schema.teaching_candidates,
                    key=lambda c: c.readiness_score,
                    reverse=True
                )[:8]
                result["teaching_candidates"] = [t.model_dump() for t in top_teaching]
                result["goal_candidates"] = []  # Goal already identified
                # Ensure user_goal is prominently available
                result["user_goal"] = schema.interview_state.user_goal
                
                # Include prior knowledge assessment for teaching calibration
                result["prior_knowledge_assessment"] = schema.prior_knowledge_assessment.model_dump()
                result["assessment_confidence"] = schema.prior_knowledge_assessment.confidence
                
                # Include task curriculum state
                result["task_curriculum"] = schema.task_curriculum.model_dump()

            return result
        except Exception:
            # Worst case, fall back to full dump.
            return schema.model_dump()
