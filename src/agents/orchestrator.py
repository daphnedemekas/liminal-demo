"""Orchestrator for coordinating discovery conversation."""
from typing import Optional, Generator
import uuid
from src.agents.interviewer import InterviewerAgent
from src.agents.goal_discovery_ranker import GoalDiscoveryRanker
from src.agents.teaching_candidate_ranker import TeachingCandidateRanker
from src.agents.ranker_base import RankerAgentBase
from src.database.manager import DatabaseManager
from src.schema.full_schema import (
    DiscoverySchema,
    UserProfile,
    InterviewState,
    Controller
)
from src.llm_client import LLMClient


class DiscoveryOrchestrator:
    """
    Orchestrates the discovery conversation by coordinating:
    - Interviewer agent (asks questions)
    - Ranker agents (analyze and update schema)
      - GoalDiscoveryRanker (Phase 1: find learning goal)
      - TeachingCandidateRanker (Phase 2: find teaching target)
    - Database (persists user profiles and sessions)

    The orchestrator switches between rankers based on goal_identified state.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        db_path: str = "data/liminal.db",
        model_config: Optional[dict] = None,
        user_goal: Optional[str] = None,
        session_id: Optional[str] = None,  # If provided, resume existing session
        conversation_history: Optional[list] = None,  # Pre-loaded conversation history
        schema_state: Optional[dict] = None  # Pre-loaded schema state for resuming
    ):
        """
        Initialize discovery orchestrator.

        Args:
            user_id: User identifier (if None, creates new user)
            db_path: Path to SQLite database
            model_config: Optional model configuration override
                         e.g., {"interviewer": "cerebras:llama-3.3-70b", "ranker": "anthropic:claude-sonnet-4-20250514"}
            user_goal: Optional learning goal for goal-directed discovery (skips Phase 1)
            session_id: Optional existing session ID to resume
            conversation_history: Optional pre-loaded conversation history
            schema_state: Optional pre-loaded schema state
        """
        # Initialize components
        self.llm = LLMClient()
        self.model_config = model_config or {}
        self.interviewer = InterviewerAgent(self.llm)
        self.user_goal = user_goal  # Store for schema initialization

        # Initialize BOTH rankers - orchestrator switches between them
        ranker_model = self.model_config.get("ranker")
        self.goal_discovery_ranker = GoalDiscoveryRanker(self.llm, model_config=ranker_model)
        self.teaching_candidate_ranker = TeachingCandidateRanker(self.llm, model_config=ranker_model)

        if user_goal:
            print(f"[Orchestrator] Goal provided: '{user_goal}' - starting in Phase 2")
        else:
            print("[Orchestrator] No goal provided - starting in Phase 1 (Goal Discovery)")

        self.db = DatabaseManager(db_path)
        self._last_phase = None  # Track phase for logging transitions

        # User and session tracking
        self.user_id = user_id or str(uuid.uuid4())
        
        # Resume existing session or create new one
        if session_id:
            self.session_id = session_id
            print(f"[Orchestrator] Resuming session: {session_id[:8]}...")
        else:
            self.session_id = str(uuid.uuid4())
            print(f"[Orchestrator] Creating new session: {self.session_id[:8]}...")

        # Load or create user profile from database
        db_user = self.db.get_or_create_user(self.user_id)
        
        # Only create new session entry if this is a new session
        if not session_id:
            self.db.create_session(self.session_id, self.user_id)

        # Initialize or restore schema
        if schema_state:
            print(f"[Orchestrator] Restoring schema state from database...")
            self.schema = DiscoverySchema(**schema_state)
            # Update goal from restored state if available
            if self.schema.interview_state.user_goal:
                self.user_goal = self.schema.interview_state.user_goal
                print(f"[Orchestrator] Restored goal: {self.user_goal}")
        else:
            self.schema = self._initialize_schema(db_user)
        
        # Initialize or restore conversation history
        self.conversation_history = conversation_history or []
        if conversation_history:
            print(f"[Orchestrator] Restored {len(conversation_history)} messages from history")

    def start(self) -> str:
        """
        Start conversation - returns empty string since we go straight to contextual response.

        Returns:
            Empty string (the real opening comes after user sends background)
        """
        # No opening message - we wait for user background and then generate contextual response
        return ""

    def process_user_message(self, user_message: str) -> str:
        """
        Process user message through Ranker → Interviewer pipeline.

        Args:
            user_message: User's message

        Returns:
            Next question from interviewer
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Check if this is the first user message (onboarding background)
        is_first_message = len([m for m in self.conversation_history if m["role"] == "user"]) == 1

        # If this is the first message, generate contextual opening question
        if is_first_message:
            # Check if user has a goal
            user_goal = self.schema.interview_state.user_goal if self.schema.interview_state.goal_provided else None

            if user_goal:
                print(f"[Interviewer] Generating goal-directed opening question (goal: {user_goal})...")
                opening_question = self.interviewer.generate_goal_directed_opening(
                    user_background=user_message,
                    goal=user_goal
                )
            else:
                print("[Interviewer] Generating contextual opening question based on user background...")
                opening_question = self.interviewer.generate_contextual_opening(user_background=user_message)

            # Add to history
            self.conversation_history.append({
                "role": "assistant",
                "content": opening_question
            })

            # Save conversation history to database (so it persists across navigations)
            print("[DB] Saving opening question to conversation history...")
            self.db.save_conversation_history(self.session_id, self.conversation_history)

            return opening_question

        # Step 1: Select appropriate ranker and update schema
        ranker = self._get_ranker()
        print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
        self.schema = ranker.update_schema(
            self.schema,
            self.conversation_history,
            user_message
        )

        # Debug output for controller state
        if self.schema.controller:
            ctrl = self.schema.controller
            print(f"[CONTROLLER] Mode: {ctrl.conversation_mode}, Target: {ctrl.target_ambiguity}")
            print(f"[CONTROLLER] Intent: {ctrl.question_intent}")
            suggested = ctrl.focus_instruction or "(none)"
            print(f"[CONTROLLER] Focus: {suggested[:100]}..." if len(suggested) > 100 else f"[CONTROLLER] Focus: {suggested}")
            print(f"[CONTROLLER] Recent intents: {self.schema.interview_state.recent_question_intents}")
            if ctrl.target_teaching_candidate_id:
                cand = next(
                    (c for c in self.schema.teaching_candidates 
                     if c.id == ctrl.target_teaching_candidate_id),
                    None
                )
                if cand:
                    print(f"[CONTROLLER] Candidate: {cand.topic}, Stakes: {cand.stakes_clarified}")

        # Step 2: Save schema state to database
        print("[DB] Saving session state...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())

        # Step 3: Update user profile in database
        print("[DB] Updating user profile in database...")
        profile_updates = {
            "curiosity_type": self.schema.user_profile.curiosity_type.model_dump(),
            "entry_mode": self.schema.user_profile.entry_mode.model_dump(),
            "uncertainty_tolerance": self.schema.user_profile.uncertainty_tolerance.model_dump(),
            "interest_phase_default": self.schema.user_profile.interest_phase_default.model_dump(),
            "motivation_profile": self.schema.user_profile.motivation_profile.model_dump(),
            "pacing_preference": self.schema.user_profile.pacing_preference.model_dump(),
            "riasec_hint": self.schema.user_profile.riasec_hint.model_dump(),
            "communication_style": self.schema.user_profile.communication_style.model_dump()
        }
        self.db.update_user_profile(self.user_id, profile_updates)
        print(f"[DB] Profile updated for user {self.user_id[:8]}...")

        # Step 4a: Check if a goal has been proposed (needs user confirmation)
        if self.schema.interview_state.proposed_goal and not self.schema.interview_state.goal_identified:
            print(f"[Orchestrator] Goal proposed: '{self.schema.interview_state.proposed_goal}'")
            # Return special marker that tells the caller to show goal confirmation UI
            return f"__GOAL_PROPOSED__:{self.schema.interview_state.proposed_goal}"

        # Step 4b: Check if a teaching candidate has been proposed (needs user confirmation)
        if self.schema.interview_state.proposed_teaching_id and not self.schema.interview_state.teaching_candidate_identified:
            # Find the proposed candidate
            proposed_candidate = next(
                (c for c in self.schema.teaching_candidates 
                 if c.id == self.schema.interview_state.proposed_teaching_id),
                None
            )
            if proposed_candidate:
                print(f"[Orchestrator] Teaching candidate proposed: '{proposed_candidate.topic}'")
                # Return special marker with candidate info
                candidate_info = {
                    "id": proposed_candidate.id,
                    "topic": proposed_candidate.topic,
                    "focus_question": proposed_candidate.focus_question,
                    "identified_gap": proposed_candidate.identified_gap,
                    "readiness_score": proposed_candidate.readiness_score
                }
                import json
                return f"__TEACHING_PROPOSED__:{json.dumps(candidate_info)}"

        # Step 4c: Check if ready for teaching
        if self.schema.teaching_recommendation.ready:
            print("[Orchestrator] Ready for teaching phase!")
            return self._create_transition_message()

        # Step 5: Interviewer generates next question
        print("[Interviewer] Generating next question...")
        next_question = self.interviewer.generate_next_question(
            self.schema,
            self.conversation_history
        )

        # Check if a cognitive framework was used
        if self.interviewer.contains_framework(next_question):
            self.schema.interview_state.frameworks_offered += 1
            print(f"[Interviewer] Framework detected. Total frameworks offered: {self.schema.interview_state.frameworks_offered}")

        # Track question to avoid repetition
        if self.schema.controller.question_intent:
            self.schema.interview_state.recent_question_intents.append(self.schema.controller.question_intent)
            # Keep only last 5
            self.schema.interview_state.recent_question_intents = self.schema.interview_state.recent_question_intents[-5:]
        
        # Store brief summary of question (first 50 chars)
        question_summary = next_question[:50] + "..." if len(next_question) > 50 else next_question
        self.schema.interview_state.recent_question_summaries.append(question_summary)
        self.schema.interview_state.recent_question_summaries = self.schema.interview_state.recent_question_summaries[-5:]

        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": next_question
        })

        # Save updated schema AND conversation history to database
        print("[DB] Saving updated schema and conversation history...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)

        return next_question

    def process_user_message_stream(self, user_message: str) -> Generator[str, None, None]:
        """
        Process user message and stream the response.
        
        This is a streaming version of process_user_message for better UX.
        Yields chunks as the interviewer generates them.
        
        Args:
            user_message: User's message
            
        Yields:
            Text chunks as they stream in
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Check if this is the first user message (onboarding background)
        is_first_message = len([m for m in self.conversation_history if m["role"] == "user"]) == 1

        # If this is the first message, generate contextual opening question (non-streaming for simplicity)
        if is_first_message:
            # Check if user has a goal
            user_goal = self.schema.interview_state.user_goal if self.schema.interview_state.goal_provided else None

            if user_goal:
                print(f"[Interviewer] Generating goal-directed opening question (goal: {user_goal})...")
                opening_question = self.interviewer.generate_goal_directed_opening(
                    user_background=user_message,
                    goal=user_goal
                )
            else:
                print("[Interviewer] Generating contextual opening question based on user background...")
                opening_question = self.interviewer.generate_contextual_opening(user_background=user_message)

            self.conversation_history.append({
                "role": "assistant",
                "content": opening_question
            })
            
            # Save conversation history to database (so it persists across navigations)
            print("[DB] Saving opening question to conversation history...")
            self.db.save_conversation_history(self.session_id, self.conversation_history)
            
            yield opening_question
            return

        # Step 1: Select appropriate ranker and update schema (blocking - must complete before interviewer)
        ranker = self._get_ranker()
        print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
        self.schema = ranker.update_schema(
            self.schema,
            self.conversation_history,
            user_message
        )

        # Debug output for ambiguity targeting
        if self.schema.controller:
            ctrl = self.schema.controller
            if ctrl.target_ambiguity or ctrl.conversation_mode:
                print(f"[DEBUG] Mode: {ctrl.conversation_mode}")
                print(f"[DEBUG] Target: {ctrl.target_ambiguity}")
                if ctrl.target_teaching_candidate_id:
                    cand = next(
                        (c for c in self.schema.teaching_candidates 
                         if c.id == ctrl.target_teaching_candidate_id),
                        None
                    )
                    if cand:
                        print(f"[DEBUG] Candidate: {cand.topic}")
                        print(f"[DEBUG] Stakes clarified: {cand.stakes_clarified}")

        # Step 2: Save schema state to database
        print("[DB] Saving session state...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())

        # Step 3: Update user profile in database
        print("[DB] Updating user profile in database...")
        profile_updates = {
            "curiosity_type": self.schema.user_profile.curiosity_type.model_dump(),
            "entry_mode": self.schema.user_profile.entry_mode.model_dump(),
            "uncertainty_tolerance": self.schema.user_profile.uncertainty_tolerance.model_dump(),
            "interest_phase_default": self.schema.user_profile.interest_phase_default.model_dump(),
            "motivation_profile": self.schema.user_profile.motivation_profile.model_dump(),
            "pacing_preference": self.schema.user_profile.pacing_preference.model_dump(),
            "riasec_hint": self.schema.user_profile.riasec_hint.model_dump(),
            "communication_style": self.schema.user_profile.communication_style.model_dump()
        }
        self.db.update_user_profile(self.user_id, profile_updates)
        print(f"[DB] Profile updated for user {self.user_id[:8]}...")

        # Step 4: Check if ready for teaching
        if self.schema.teaching_recommendation.ready:
            print("[Orchestrator] Ready for teaching phase!")
            transition_msg = self._create_transition_message()
            yield transition_msg
            return

        # Step 5: Stream interviewer response
        print("[Interviewer] Streaming next question...")
        full_response = ""
        for chunk in self.interviewer.generate_next_question_stream(
            self.schema,
            self.conversation_history
        ):
            full_response += chunk
            yield chunk

        # Check if a cognitive framework was used
        if self.interviewer.contains_framework(full_response):
            self.schema.interview_state.frameworks_offered += 1
            print(f"[Interviewer] Framework detected. Total frameworks offered: {self.schema.interview_state.frameworks_offered}")

        # Track question to avoid repetition (same as non-streaming version)
        if self.schema.controller.question_intent:
            self.schema.interview_state.recent_question_intents.append(self.schema.controller.question_intent)
            self.schema.interview_state.recent_question_intents = self.schema.interview_state.recent_question_intents[-5:]

        question_summary = full_response[:50] + "..." if len(full_response) > 50 else full_response
        self.schema.interview_state.recent_question_summaries.append(question_summary)
        self.schema.interview_state.recent_question_summaries = self.schema.interview_state.recent_question_summaries[-5:]

        # Save updated schema with question history to database
        print("[DB] Saving updated schema with question history...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())

        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })

    def _get_ranker(self) -> RankerAgentBase:
        """
        Select the appropriate ranker based on current phase.

        Phase 1 (Goal Discovery): Use GoalDiscoveryRanker
        Phase 2 (Teaching Discovery): Use TeachingCandidateRanker

        Returns:
            The appropriate ranker for the current phase
        """
        if self.schema.interview_state.goal_identified:
            current_phase = "Phase 2 (Teaching Discovery)"
            ranker = self.teaching_candidate_ranker
        else:
            current_phase = "Phase 1 (Goal Discovery)"
            ranker = self.goal_discovery_ranker

        # Log phase transitions
        if self._last_phase != current_phase:
            if self._last_phase is not None:
                print(f"\n[Orchestrator] ===== PHASE TRANSITION =====")
                print(f"[Orchestrator] {self._last_phase} -> {current_phase}")
                if self.schema.interview_state.user_goal:
                    print(f"[Orchestrator] Goal: '{self.schema.interview_state.user_goal}'")
            self._last_phase = current_phase

        return ranker

    def _initialize_schema(self, db_user) -> DiscoverySchema:
        """
        Initialize schema from database user profile.

        Args:
            db_user: UserProfile from database

        Returns:
            Initialized DiscoverySchema
        """
        # Build user profile from database
        user_profile = UserProfile(
            curiosity_type=db_user.curiosity_type or {"value": None, "confidence": 0.0, "evidence": []},
            entry_mode=db_user.entry_mode or {"people": 0.0, "problems": 0.0, "ideas": 0.0},
            uncertainty_tolerance=db_user.uncertainty_tolerance or {"value": None, "confidence": 0.0, "evidence": []},
            interest_phase_default=db_user.interest_phase_default or {"value": None, "confidence": 0.0, "notes": ""},
            motivation_profile=db_user.motivation_profile or {
                "intrinsic_value": 0.0,
                "utility_value": 0.0,
                "identity_value": 0.0,
                "perceived_cost": 0.0
            },
            pacing_preference=db_user.pacing_preference or {"value": None, "confidence": 0.0},
            riasec_hint=db_user.riasec_hint or {"I": 0.0, "A": 0.0, "S": 0.0, "R": 0.0, "E": 0.0, "C": 0.0},
            communication_style=db_user.communication_style or {
                "verbosity": "medium",
                "complexity": "medium",
                "emotional_expression": "neutral",
                "question_asking_frequency": "medium"
            }
        )

        # Initialize interview state with goal if provided
        interview_state = InterviewState()
        if self.user_goal:
            interview_state.goal_provided = True
            interview_state.goal_identified = True  # Skip Phase 1
            interview_state.user_goal = self.user_goal

        # Initialize schema
        return DiscoverySchema(
            session_id=self.session_id,
            user_profile=user_profile,
            signals=[],
            interview_state=interview_state,
            controller=Controller(
                next_action="ask_opening",
                focus_instruction="",
                question_intent="general_explore",
                fallback_questions=[],
                branch_condition="unclear"
            )
        )

    def accept_proposed_goal(self) -> dict:
        """
        User accepted the proposed goal. Return data for frontend to create new goal panel.

        NOTE: Does NOT transition this session - exploration continues.
        Frontend creates a separate goal panel session.

        Returns:
            Dict with goal data for panel creation
        """
        if not self.schema.interview_state.proposed_goal:
            return {"error": "No goal to accept."}

        goal = self.schema.interview_state.proposed_goal
        goal_id = self.schema.interview_state.proposed_goal_id

        # Track this goal as accepted so we don't re-propose it
        if goal_id is not None:
            self.schema.interview_state.accepted_goal_ids.append(goal_id)
        
        # Record turn number for cooldown (don't propose another goal immediately)
        self.schema.interview_state.last_goal_accepted_turn = self.schema.interview_state.turns_elapsed

        # Clear proposal but stay in Phase 1 (exploration continues)
        self.schema.interview_state.proposed_goal = None
        self.schema.interview_state.proposed_goal_id = None
        # goal_identified stays False - can discover more goals

        print(f"\n[Orchestrator] ===== GOAL ACCEPTED =====")
        print(f"[Orchestrator] Goal: '{goal}'")
        print(f"[Orchestrator] Exploration continues - frontend creates goal panel")

        # Add acceptance to conversation history
        confirmation_message = f"Great! I'll help you explore **{goal}** in a new panel. You can continue exploring other interests here."
        self.conversation_history.append({
            "role": "user",
            "content": "[Accepted goal]"
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": confirmation_message
        })

        # Save the updated state AND conversation history
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)

        return {
            "success": True,
            "goal": goal,
            "goal_id": goal_id,
            "message": confirmation_message
        }
    
    def reject_proposed_goal(self) -> str:
        """
        User rejected the proposed goal. Continue in Phase 1 and generate a response
        to the user's last message.
        
        Returns:
            Next question from interviewer (responding to what user actually said)
        """
        if not self.schema.interview_state.proposed_goal:
            return "No goal to reject."
        
        goal = self.schema.interview_state.proposed_goal
        goal_id = self.schema.interview_state.proposed_goal_id
        
        # Mark this goal as rejected so we don't propose it again
        if goal_id is not None:
            self.schema.interview_state.rejected_goal_ids.append(goal_id)
        
        # Clear the proposal
        self.schema.interview_state.proposed_goal = None
        self.schema.interview_state.proposed_goal_id = None
        
        print(f"\n[Orchestrator] ===== GOAL REJECTED =====")
        print(f"[Orchestrator] Goal: '{goal}'")
        print(f"[Orchestrator] Continuing in Phase 1 (Goal Discovery)")
        
        # Add rejection to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": "[Rejected goal - keep exploring]"
        })
        
        # Generate a real response to the user's last message using the interviewer
        print("[Interviewer] Generating response after goal rejection...")
        next_question = self.interviewer.generate_next_question(
            self.schema,
            self.conversation_history
        )
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": next_question
        })
        
        # Save updated state AND conversation history
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)
        
        return next_question

    def accept_proposed_teaching(self) -> dict:
        """
        User accepted the proposed teaching candidate. Return data for frontend to create teaching panel.

        NOTE: Does NOT transition this session - goal panel continues.
        Frontend creates a separate teaching panel session.

        Returns:
            Dictionary with candidate info for panel creation
        """
        if not self.schema.interview_state.proposed_teaching_id:
            return {"success": False, "message": "No teaching candidate to accept."}

        # Find the proposed candidate
        candidate = next(
            (c for c in self.schema.teaching_candidates
             if c.id == self.schema.interview_state.proposed_teaching_id),
            None
        )

        if not candidate:
            return {"success": False, "message": "Teaching candidate not found."}

        # Clear proposal but stay in Phase 2 (goal panel continues discovering teaching targets)
        self.schema.interview_state.proposed_teaching_id = None
        # teaching_candidate_identified stays False - can discover more teaching targets

        print(f"\n[Orchestrator] ===== TEACHING CANDIDATE ACCEPTED =====")
        print(f"[Orchestrator] Topic: '{candidate.topic}'")
        print(f"[Orchestrator] Goal panel continues - frontend creates teaching panel")

        # Add acceptance to conversation history
        confirmation_message = f"Perfect! Let's start learning about **{candidate.topic}**."
        self.conversation_history.append({
            "role": "user",
            "content": "[Accepted teaching topic]"
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": confirmation_message
        })

        # Save the updated state AND conversation history
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)

        return {
            "success": True,
            "message": confirmation_message,
            "candidate": {
                "id": candidate.id,
                "topic": candidate.topic,
                "focus_question": candidate.focus_question,
                "identified_gap": candidate.identified_gap
            }
        }
    
    def reject_proposed_teaching(self) -> str:
        """
        User rejected the proposed teaching candidate. Continue finding alternatives.
        
        Returns:
            Next question from interviewer
        """
        if not self.schema.interview_state.proposed_teaching_id:
            return "No teaching candidate to reject."
        
        teaching_id = self.schema.interview_state.proposed_teaching_id
        
        # Find the rejected candidate for logging
        candidate = next(
            (c for c in self.schema.teaching_candidates 
             if c.id == teaching_id),
            None
        )
        topic = candidate.topic if candidate else "unknown"
        
        # Mark this candidate as rejected so we don't propose it again
        self.schema.interview_state.rejected_teaching_ids.append(teaching_id)
        
        # Clear the proposal
        self.schema.interview_state.proposed_teaching_id = None
        
        print(f"\n[Orchestrator] ===== TEACHING CANDIDATE REJECTED =====")
        print(f"[Orchestrator] Topic: '{topic}'")
        print(f"[Orchestrator] Continuing to find better starting point...")
        
        # Add rejection to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": "[Rejected topic - find another starting point]"
        })
        
        # Generate a real response exploring alternatives
        print("[Interviewer] Generating response after teaching rejection...")
        next_question = self.interviewer.generate_next_question(
            self.schema,
            self.conversation_history
        )
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": next_question
        })
        
        # Save updated state AND conversation history
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)
        
        return next_question

    def _create_transition_message(self) -> str:
        """
        Create handoff to teaching phase.

        Returns:
            Transition message
        """
        rec = self.schema.teaching_recommendation

        if rec.first_move:
            return rec.first_move
        else:
            # Fallback transition
            return f"Okay, so you want to understand {rec.target_topic}. Let's dive in."

    def get_schema(self) -> dict:
        """
        Return current schema for debugging.

        Returns:
            Schema as dictionary
        """
        return self.schema.model_dump()

    def is_complete(self) -> bool:
        """
        Check if discovery phase is complete and ready for teaching.

        Returns:
            True if ready to transition to teaching phase
        """
        return self.schema.teaching_recommendation.ready

    def get_final_topic(self):
        """
        Get final topic information for teaching phase.

        Returns:
            FinalTopic object with topic details
        """
        # Create a simple object with the final topic data
        class FinalTopic:
            def __init__(self, schema):
                rec = schema.teaching_recommendation
                self.topic = rec.target_topic or "Unknown topic"
                self.user_confusion = rec.focus_question or ""
                self.stakes = ""  # Could extract from schema if needed
                self.learning_hook = rec.first_move or ""
                self.suggested_angles = [rec.angle] if rec.angle else []
                self.scores = None  # No scores structure in current schema

        return FinalTopic(self.schema)

    def end_session(self):
        """End the session and save final state."""
        final_topic = None
        if self.schema.teaching_recommendation.ready:
            final_topic = self.schema.teaching_recommendation.target_topic

        self.db.end_session(self.session_id, final_topic)
        print(f"[Orchestrator] Session ended. Total tokens used: {self.llm.get_total_tokens()}")
