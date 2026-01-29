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
        schema_state: Optional[dict] = None,  # Pre-loaded schema state for resuming
        exploration_history: Optional[list] = None  # Exploration conversation history for goal sessions
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

        self.db = DatabaseManager(db_path=db_path)
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

        # Store user's existing background info (from onboarding/exploration)
        self.user_background = db_user.onboarding_info if db_user.onboarding_info else None
        if self.user_background:
            print(f"[Orchestrator] Found existing user background ({len(self.user_background)} chars)")

        # Only create new session entry if this is a new session
        if not session_id:
            self.db.create_session(self.session_id, self.user_id)

        # Initialize or restore schema
        if schema_state:
            print(f"[Orchestrator] Restoring schema state from database...")
            # Fix communication_style if it has None values
            if "user_profile" in schema_state and schema_state["user_profile"]:
                user_profile_data = schema_state["user_profile"]
                if "communication_style" in user_profile_data:
                    comm_style = user_profile_data["communication_style"]
                    if comm_style is None or any(v is None for v in (comm_style.values() if isinstance(comm_style, dict) else [])):
                        # Ensure all fields have defaults
                        user_profile_data["communication_style"] = {
                            "verbosity": (comm_style.get("verbosity") if isinstance(comm_style, dict) else None) or "medium",
                            "complexity": (comm_style.get("complexity") if isinstance(comm_style, dict) else None) or "medium",
                            "emotional_expression": (comm_style.get("emotional_expression") if isinstance(comm_style, dict) else None) or "neutral",
                            "question_asking_frequency": (comm_style.get("question_asking_frequency") if isinstance(comm_style, dict) else None) or "medium"
                        }
            
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
        
        # Store exploration history for goal sessions (context from exploration chat)
        self.exploration_history = exploration_history or []
        if exploration_history:
            print(f"[Orchestrator] Loaded {len(exploration_history)} messages from exploration chat for context")

    def start(self) -> str:
        """
        Start conversation.

        For goal sessions with existing user background, returns goal-directed opening.
        For new users or exploration, returns empty (waits for user to provide background).

        Returns:
            Opening message or empty string
        """
        # For goal sessions with existing user background, generate opening directly
        if self.user_goal and self.user_background and len(self.conversation_history) == 0:
            print(f"[Orchestrator] Goal session with existing user - generating opening directly")
            # Check if we have exploration conversation history (from when goal was created)
            exploration_context = getattr(self, 'exploration_history', None)
            if exploration_context:
                print(f"[Orchestrator] Using {len(exploration_context)} messages from exploration chat as context")
            opening_question = self.interviewer.generate_goal_directed_opening(
                user_background=self.user_background,
                goal=self.user_goal,
                exploration_context=exploration_context
            )
            self.conversation_history.append({
                "role": "assistant",
                "content": opening_question
            })
            self.db.save_conversation_history(self.session_id, self.conversation_history)
            return opening_question

        # For new users or exploration, wait for user to provide background
        return ""

    def process_user_message(self, user_message: str, skip_history: bool = False) -> str:
        """
        Process user message through Ranker → Interviewer pipeline.

        Args:
            user_message: User's message
            skip_history: If True, don't add this message to conversation history (for onboarding)

        Returns:
            Next question from interviewer
        """
        # Check if this is the first user message (onboarding background)
        is_first_message = len([m for m in self.conversation_history if m["role"] == "user"]) == 0

        # If this is the first message and no conversation started yet, add onboarding question
        # (Goal sessions with existing background already have an opening from start())
        if is_first_message and len(self.conversation_history) == 0:
            # New user or exploration session - ask for background
            opening_prompt = "Tell me about yourself. What do you do, what are you interested in, and what's been on your mind lately? Do you have particular hobbies, projects, or curiosities, or do you just want to brainstorm?"
            self.conversation_history.append({
                "role": "assistant",
                "content": opening_prompt
            })
        
        # Add user message to history (unless it's onboarding that should be hidden)
        if not skip_history:
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })
            # Save user message to database IMMEDIATELY so it persists even if user refreshes
            print("[DB] Saving user message to conversation history immediately...")
            self.db.save_conversation_history(self.session_id, self.conversation_history)
        else:
            print("[Orchestrator] Skipping adding onboarding message to visible conversation history")

        # For first message: Generate response FIRST, then run ranker (faster UX)
        # The opening question doesn't need ranker output - it only uses user_background
        # BUT: If start() already generated an opening (goal session with background), don't generate another one
        has_existing_opening = len([m for m in self.conversation_history if m["role"] == "assistant"]) > 0
        
        if is_first_message and not has_existing_opening:
            # Check if user has a goal (from schema init, not ranker)
            user_goal = self.user_goal  # Use stored goal from __init__

            if user_goal:
                print(f"[Interviewer] Generating goal-directed opening question (goal: {user_goal})...")
                # Check if we have exploration conversation history
                exploration_context = getattr(self, 'exploration_history', None)
                opening_question = self.interviewer.generate_goal_directed_opening(
                    user_background=user_message,
                    goal=user_goal,
                    exploration_context=exploration_context
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

            # NOW run ranker to extract themes/goals for next turn (after user sees response)
            print("[Ranker] Running ranker in background after first response...")
            ranker = self._get_ranker()
            self.schema = ranker.update_schema(
                self.schema,
                self.conversation_history,
                user_message
            )
            # Save schema state
            self.db.save_session_state(self.session_id, self.schema.model_dump())

            return opening_question
        elif is_first_message and has_existing_opening and skip_history:
            # Opening already exists from start() and this is onboarding (skip_history=True)
            # Just update the schema with onboarding info, don't generate a response
            print("[Orchestrator] Opening already exists, processing onboarding silently (updating schema only)...")
            ranker = self._get_ranker()
            self.schema = ranker.update_schema(
                self.schema,
                self.conversation_history,
                user_message
            )
            self.db.save_session_state(self.session_id, self.schema.model_dump())
            # Return empty string - no response needed, opening already shown
            return ""

        # Delegate to phase-specific handler
        if self.schema.interview_state.goal_identified:
            return self._process_phase2_message(user_message)
        else:
            return self._process_phase1_message(user_message)

    def process_user_message_events(self, user_message: str, skip_history: bool = False):
        """
        Streaming version of process_user_message that yields typed events.

        Each event is a dict with a "type" key:
          - {"type": "stream_start"}
          - {"type": "stream_chunk", "content": "..."}
          - {"type": "stream_end", "content": "full text"}
          - {"type": "goal_proposed", "goal": "..."}
          - {"type": "curriculum_proposed", "response": dict}
          - {"type": "empty"} — no response needed
          - {"type": "complete", "content": "full text"} — non-streamed complete response

        Args:
            user_message: User's message
            skip_history: If True, don't add to conversation history

        Yields:
            Event dicts
        """
        # --- Identical preamble to process_user_message ---
        is_first_message = len([m for m in self.conversation_history if m["role"] == "user"]) == 0

        if is_first_message and len(self.conversation_history) == 0:
            opening_prompt = "Tell me about yourself. What do you do, what are you interested in, and what's been on your mind lately? Do you have particular hobbies, projects, or curiosities, or do you just want to brainstorm?"
            self.conversation_history.append({"role": "assistant", "content": opening_prompt})

        if not skip_history:
            self.conversation_history.append({"role": "user", "content": user_message})
            self.db.save_conversation_history(self.session_id, self.conversation_history)
        else:
            print("[Orchestrator] Skipping adding onboarding message to visible conversation history")

        has_existing_opening = len([m for m in self.conversation_history if m["role"] == "assistant"]) > 0

        # First message: non-streaming (opening question, then ranker in background)
        if is_first_message and not has_existing_opening:
            user_goal = self.user_goal
            if user_goal:
                exploration_context = getattr(self, 'exploration_history', None)
                opening_question = self.interviewer.generate_goal_directed_opening(
                    user_background=user_message, goal=user_goal,
                    exploration_context=exploration_context
                )
            else:
                opening_question = self.interviewer.generate_contextual_opening(user_background=user_message)

            self.conversation_history.append({"role": "assistant", "content": opening_question})
            self.db.save_conversation_history(self.session_id, self.conversation_history)

            yield {"type": "complete", "content": opening_question}

            # Run ranker after yielding response
            ranker = self._get_ranker()
            self.schema = ranker.update_schema(self.schema, self.conversation_history, user_message)
            self.db.save_session_state(self.session_id, self.schema.model_dump())
            return

        if is_first_message and has_existing_opening and skip_history:
            ranker = self._get_ranker()
            self.schema = ranker.update_schema(self.schema, self.conversation_history, user_message)
            self.db.save_session_state(self.session_id, self.schema.model_dump())
            yield {"type": "empty"}
            return

        # --- Phase-specific handling with streaming ---
        if self.schema.interview_state.goal_identified:
            yield from self._process_phase2_message_events(user_message)
        else:
            yield from self._process_phase1_message_events(user_message)

    def _process_phase1_message_events(self, user_message: str):
        """Phase 1 streaming: run ranker, then stream interviewer (or yield goal proposal)."""
        ranker = self._get_ranker()
        print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
        self.schema = ranker.update_schema(self.schema, self.conversation_history, user_message)
        self._log_controller_state()
        self._save_schema_and_profile()

        # Goal proposed — not streamable, yield as single event
        if self.schema.interview_state.proposed_goal and not self.schema.interview_state.goal_identified:
            print(f"[Orchestrator] Goal proposed: '{self.schema.interview_state.proposed_goal}'")
            yield {"type": "goal_proposed", "goal": self.schema.interview_state.proposed_goal}
            return

        # Stream the interviewer response
        yield from self._stream_interviewer_response(user_message)

    def _process_phase2_message_events(self, user_message: str):
        """Phase 2 streaming: run ranker (unless curriculum modification), then stream interviewer."""
        is_curriculum_modification = (
            self.schema.task_curriculum.proposed and
            not self.schema.task_curriculum.accepted and
            self.schema.controller.conversation_mode == "negotiate_curriculum" and
            self.schema.controller.next_action == "propose_task_curriculum"
        )

        if is_curriculum_modification:
            print("[Orchestrator] Curriculum modification detected - skipping ranker")
        else:
            ranker = self._get_ranker()
            print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
            self.schema = ranker.update_schema(self.schema, self.conversation_history, user_message)

        self._log_controller_state()
        self._save_schema_and_profile()

        # Stream interviewer (handles curriculum proposals as single dict yields)
        yield from self._stream_interviewer_response(user_message)

    def _stream_interviewer_response(self, user_message: str):
        """Stream interviewer response, handling both text chunks and curriculum proposal dicts."""
        print("[Interviewer] Generating streaming response...")

        full_response = ""
        stream_started = False

        for item in self.interviewer.generate_response_stream(user_message, self.schema, self.conversation_history):
            # Dict = curriculum proposal (not streamable)
            if isinstance(item, dict) and item.get("type") == "curriculum_proposal":
                result = self._handle_curriculum_proposal(item)
                yield {"type": "curriculum_proposed", "response": item, "marker": result}
                return

            # String chunk = streaming text
            if not stream_started:
                yield {"type": "stream_start"}
                stream_started = True

            full_response += item
            yield {"type": "stream_chunk", "content": item}

        if not full_response:
            yield {"type": "empty"}
            return

        # Finalize: save to history, track metadata
        next_question = full_response
        if self.interviewer.contains_framework(next_question):
            self.schema.interview_state.frameworks_offered += 1

        if self.schema.controller.question_intent:
            self.schema.interview_state.recent_question_intents.append(self.schema.controller.question_intent)
            self.schema.interview_state.recent_question_intents = self.schema.interview_state.recent_question_intents[-5:]

        question_summary = next_question[:50] + "..." if len(next_question) > 50 else next_question
        self.schema.interview_state.recent_question_summaries.append(question_summary)
        self.schema.interview_state.recent_question_summaries = self.schema.interview_state.recent_question_summaries[-5:]

        self.conversation_history.append({"role": "assistant", "content": next_question})
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)

        yield {"type": "stream_end", "content": next_question}

    def _process_phase1_message(self, user_message: str) -> str:
        """
        Process user message in Phase 1 (Goal Discovery).

        Args:
            user_message: User's message

        Returns:
            Next question from interviewer
        """
        # Run ranker first (needed for controller guidance)
        ranker = self._get_ranker()
        print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
        self.schema = ranker.update_schema(
            self.schema,
            self.conversation_history,
            user_message
        )

        # Debug output for controller state
        self._log_controller_state()

        # Save schema state and update user profile
        self._save_schema_and_profile()

        # Check if a goal has been proposed (needs user confirmation)
        if self.schema.interview_state.proposed_goal and not self.schema.interview_state.goal_identified:
            print(f"[Orchestrator] Goal proposed: '{self.schema.interview_state.proposed_goal}'")
            # Return special marker that tells the caller to show goal confirmation UI
            return f"__GOAL_PROPOSED__:{self.schema.interview_state.proposed_goal}"

        # Generate and return interviewer response
        return self._generate_and_save_response(user_message)

    def _process_phase2_message(self, user_message: str) -> str:
        """
        Process user message in Phase 2 (Teaching Discovery).

        Args:
            user_message: User's message

        Returns:
            Next question from interviewer
        """
        # Note: Curriculum acceptance is handled via button clicks in the frontend,
        # which sends the __ACCEPT_CURRICULUM__ command directly to the backend.
        # We don't detect text-based acceptance here to avoid false positives.

        # Check if this is a curriculum modification request
        # If curriculum is proposed but not accepted, and controller is in negotiate mode,
        # we can skip the full ranker pipeline and go straight to curriculum regeneration
        is_curriculum_modification = (
            self.schema.task_curriculum.proposed and 
            not self.schema.task_curriculum.accepted and
            self.schema.controller.conversation_mode == "negotiate_curriculum" and
            self.schema.controller.next_action == "propose_task_curriculum"
        )
        
        if is_curriculum_modification:
            print("[Orchestrator] Curriculum modification detected - skipping ranker for faster response")
            # Still need to update controller state, but can skip full ranker pipeline
            # The interviewer will handle the curriculum regeneration
        else:
            # Run ranker first (needed for controller guidance)
            ranker = self._get_ranker()
            print(f"[Ranker] Analyzing conversation using {ranker.__class__.__name__}...")
            self.schema = ranker.update_schema(
                self.schema,
                self.conversation_history,
                user_message
            )

        # Debug output for controller state
        self._log_controller_state()

        # Save schema state and update user profile
        self._save_schema_and_profile()

        # Generate interviewer response
        print("[Interviewer] Generating response...")
        interviewer_response = self.interviewer.generate_response(
            user_message,
            self.schema,
            self.conversation_history
        )

        # Check if interviewer returned structured curriculum proposal
        if isinstance(interviewer_response, dict) and interviewer_response.get("type") == "curriculum_proposal":
            return self._handle_curriculum_proposal(interviewer_response)

        # Check if controller wants curriculum (only happens via manual button click)
        controller_wants_curriculum = self._controller_wants_curriculum()
        
        # If controller wants curriculum, interviewer MUST return structured response
        if controller_wants_curriculum and not isinstance(interviewer_response, dict):
            print("[Orchestrator] ERROR: Controller wants curriculum but interviewer returned string instead of structured response")
            print("[Orchestrator] This should never happen - interviewer should always return dict in propose_tasks mode")
            # Continue with regular response - this is a bug that needs fixing
        
        # Extract text from structured response if needed
        if isinstance(interviewer_response, dict):
            next_question = interviewer_response["text"]
        else:
            next_question = interviewer_response

        return self._finalize_response(next_question)

    def _controller_wants_curriculum(self) -> bool:
        """Check if controller wants to propose curriculum (manual button click)."""
        return (
            self.schema.controller and 
            self.schema.controller.conversation_mode == "propose_tasks"
        )

    def _log_controller_state(self):
        """Log controller state for debugging."""
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

    def _save_schema_and_profile(self):
        """Save schema state and update user profile in database."""
        # Save schema state to database
        print("[DB] Saving session state...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())

        # Update user profile in database
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

    def _generate_and_save_response(self, user_message: str) -> str:
        """Generate interviewer response and save to history."""
        print("[Interviewer] Generating response...")
        interviewer_response = self.interviewer.generate_response(
            user_message,
            self.schema,
            self.conversation_history
        )

        # Extract text from structured response if needed
        if isinstance(interviewer_response, dict):
            next_question = interviewer_response["text"]
        else:
            next_question = interviewer_response

        return self._finalize_response(next_question)

    def _handle_curriculum_proposal(self, interviewer_response: dict) -> str:
        """Handle curriculum proposal from interviewer."""
        print("[Orchestrator] Interviewer proposed curriculum")

        # Programmatically set curriculum state (no LLM dependency!)
        from src.schema.full_schema import ProposedTask, TaskCurriculum

        # ALWAYS use tasks extracted from interviewer's response (the interviewer generates the full 8-12 task curriculum)
        # The ranker's task_curriculum.tasks are just candidates, not the full curriculum
        tasks_data = interviewer_response.get("tasks", [])
        
        if len(tasks_data) == 0:
            print("[Orchestrator] WARNING: Curriculum proposed but no tasks extracted!")
            # Fallback: Try to extract from teaching_candidates
            if len(self.schema.teaching_candidates) > 0:
                print(f"[Orchestrator] Using {len(self.schema.teaching_candidates)} teaching candidates as fallback")
                tasks_data = [
                    {
                        "id": i + 1,
                        "topic": tc.topic,
                        "justification": tc.identified_gap or "Explore this topic",
                        "prerequisites": [i] if i > 0 else [],
                        "status": "available" if i == 0 else "locked"
                    }
                    for i, tc in enumerate(self.schema.teaching_candidates[:7])
                ]
            else:
                print("[Orchestrator] ERROR: No tasks and no candidates, cannot create curriculum")
                # Return regular response instead
                next_question = interviewer_response["text"]
                # Add to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": next_question
                })
                self.db.save_session_state(self.session_id, self.schema.model_dump())
                self.db.save_conversation_history(self.session_id, self.conversation_history)
                return next_question

        # Create ProposedTask objects from extracted tasks
        tasks = [
            ProposedTask(
                id=t["id"],
                topic=t["topic"],
                justification=t["justification"],
                prerequisites=t["prerequisites"],
                status=t["status"]
            )
            for t in tasks_data
        ]

        # Set curriculum state programmatically - this is the key fix!
        self.schema.task_curriculum = TaskCurriculum(
            proposed=True,  # Set programmatically, not by ranker LLM!
            accepted=False,
            tasks=tasks,
            modification_history=[]
        )

        print(f"[Orchestrator] Set task_curriculum.proposed=True with {len(tasks)} tasks")

        # Save updated schema
        self.db.save_session_state(self.session_id, self.schema.model_dump())

        # Add the text to conversation history
        next_question = interviewer_response["text"]
        self.conversation_history.append({
            "role": "assistant",
            "content": next_question
        })
        self.db.save_conversation_history(self.session_id, self.conversation_history)

        # Return curriculum proposal marker
        import json
        curriculum_info = {
            "tasks": [t.model_dump() for t in tasks],
            "overall_justification": f"Based on your goal '{self.schema.interview_state.user_goal}' and what I've learned about your background, here's my best guess at a complete learning path. This is just a starting point - we can adjust as we go based on what works for you:"
        }
        return f"__TASK_CURRICULUM_PROPOSED__:{json.dumps(curriculum_info)}"

    def _finalize_response(self, next_question: str) -> str:
        """Finalize response by tracking metadata and saving to database."""
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
        # Generate response FIRST for fast UX, then run ranker after
        if is_first_message:
            # Check if user has a goal (from stored value, not schema)
            user_goal = self.user_goal

            if user_goal:
                print(f"[Interviewer] Generating goal-directed opening question (goal: {user_goal})...")
                # Check if we have exploration conversation history
                exploration_context = getattr(self, 'exploration_history', None)
                opening_question = self.interviewer.generate_goal_directed_opening(
                    user_background=user_message,
                    goal=user_goal,
                    exploration_context=exploration_context
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
            
            # NOW run ranker to extract themes/goals for next turn (after user sees response)
            print("[Ranker] Running ranker after first response...")
            ranker = self._get_ranker()
            self.schema = ranker.update_schema(
                self.schema,
                self.conversation_history,
                user_message
            )
            # Save schema state
            self.db.save_session_state(self.session_id, self.schema.model_dump())
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

        # Step 4: Stream interviewer response
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
        # Ensure communication_style has all required fields with defaults
        comm_style_dict = db_user.communication_style or {}
        if not comm_style_dict or any(v is None for v in comm_style_dict.values()):
            # Use defaults for any missing or None values
            comm_style_dict = {
                "verbosity": comm_style_dict.get("verbosity") or "medium",
                "complexity": comm_style_dict.get("complexity") or "medium",
                "emotional_expression": comm_style_dict.get("emotional_expression") or "neutral",
                "question_asking_frequency": comm_style_dict.get("question_asking_frequency") or "medium"
            }
        
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
            communication_style=comm_style_dict
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
        
        # Track rejection turn for cooldown (prevent immediate re-proposal)
        current_turn = self.schema.interview_state.turns_elapsed
        self.schema.interview_state.last_goal_rejected_turn = current_turn
        
        # Clear the proposal
        self.schema.interview_state.proposed_goal = None
        self.schema.interview_state.proposed_goal_id = None
        
        print(f"\n[Orchestrator] ===== GOAL REJECTED =====")
        print(f"[Orchestrator] Goal: '{goal}'")
        print(f"[Orchestrator] Continuing in Phase 1 (Goal Discovery)")
        print(f"[Orchestrator] Rejection cooldown active (turn {current_turn})")
        
        # Add rejection to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": "[Rejected goal - keep exploring]"
        })
        
        # Run ranker first to update schema and controller (needed for proper response generation)
        print("[Ranker] Running ranker after goal rejection...")
        ranker = self._get_ranker()
        self.schema = ranker.update_schema(
            self.schema,
            self.conversation_history,
            "[Rejected goal - keep exploring]"
        )
        
        # Save schema state
        self._save_schema_and_profile()
        
        # Generate a real response to the user's last message using the interviewer
        print("[Interviewer] Generating response after goal rejection...")
        next_question = self._generate_and_save_response("[Rejected goal - keep exploring]")
        
        return next_question

    def accept_proposed_curriculum(self) -> dict:
        """
        User accepted the proposed task curriculum. Return all tasks for frontend.
        First task is available, rest are locked.

        Returns:
            Dictionary with tasks info for panel creation
        """
        if not self.schema.task_curriculum.proposed:
            return {"success": False, "message": "No curriculum to accept."}

        if len(self.schema.task_curriculum.tasks) == 0:
            return {"success": False, "message": "No tasks in curriculum."}

        # Mark curriculum as accepted
        self.schema.task_curriculum.accepted = True

        # Ensure first task is available, rest are locked
        tasks = self.schema.task_curriculum.tasks
        if tasks:
            tasks[0].status = "available"
            for task in tasks[1:]:
                task.status = "locked"

        print(f"\n[Orchestrator] ===== TASK CURRICULUM ACCEPTED =====")
        print(f"[Orchestrator] {len(tasks)} tasks in curriculum")
        for i, task in enumerate(tasks):
            print(f"[Orchestrator]   {i+1}. {task.topic} ({task.status})")

        # Add acceptance to conversation history
        confirmation_message = f"Great! Your learning path has {len(tasks)} topics. Let's start with: **{tasks[0].topic}**"
        self.conversation_history.append({
            "role": "user",
            "content": "[Accepted curriculum]"
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
            "tasks": [
                {
                    "id": task.id,
                    "topic": task.topic,
                    "justification": task.justification,
                    "prerequisites": task.prerequisites,
                    "status": task.status
                }
                for task in tasks
            ]
        }

    def generate_learning_path(self) -> dict:
        """
        Manually trigger learning path (curriculum) generation.
        This is called on-demand when user clicks "Generate Learning Path" button.
        
        Returns:
            Dictionary with success status and message
        """
        # Check if goal is identified
        if not self.schema.interview_state.goal_identified:
            return {
                "success": False,
                "message": "Goal must be identified before generating a learning path."
            }
        
        # Check if we have teaching candidates
        if not self.schema.teaching_candidates or len(self.schema.teaching_candidates) == 0:
            return {
                "success": False,
                "message": "Need teaching candidates before generating a learning path. Continue the conversation to discover topics."
            }
        
        # Check if curriculum was already proposed
        if self.schema.task_curriculum.proposed:
            return {
                "success": False,
                "message": "Learning path has already been proposed. Accept or modify the existing proposal."
            }
        
        # Trigger curriculum generation by setting controller to propose_tasks mode
        print(f"[Orchestrator] ===== MANUAL LEARNING PATH GENERATION =====")
        print(f"[Orchestrator] Goal: '{self.schema.interview_state.user_goal}'")
        print(f"[Orchestrator] Teaching candidates: {len(self.schema.teaching_candidates)}")
        
        # Update controller to trigger curriculum proposal
        self.schema.controller.conversation_mode = "propose_tasks"
        self.schema.controller.next_action = "propose_task_curriculum"
        self.schema.controller.question_intent = "present_learning_path"
        self.schema.controller.focus_instruction = (
            "Based on assessment, propose a complete learning path with 8-12 sequential tasks. "
            "Include personalized justifications for each task. End with Accept/Modify options."
        )
        
        # Save updated state
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        
        # Generate the curriculum proposal directly
        # The interviewer will see propose_tasks mode and generate the curriculum
        curriculum_response = self.interviewer.generate_response(
            "",  # Empty message to trigger curriculum generation
            self.schema,
            self.conversation_history
        )
        
        # Check if we got a curriculum proposal dict
        if isinstance(curriculum_response, dict) and curriculum_response.get("type") == "curriculum_proposal":
            # Handle the curriculum proposal - this sets task_curriculum.proposed = True
            # Note: _handle_curriculum_proposal returns a marker string, but we want the actual text
            self._handle_curriculum_proposal(curriculum_response)
            
            # Extract the clean text message from the curriculum response
            curriculum_text = curriculum_response.get("text", "")
            if not curriculum_text:
                # Fallback: generate a nice message from the tasks
                tasks = curriculum_response.get("tasks", [])
                goal = self.schema.interview_state.user_goal or "your learning goal"
                curriculum_text = f"Based on your goal '{goal}' and what I've learned about your background, here's a complete learning path I've designed for you:\n\n" + "\n".join([f"{t.get('id', i+1)}. {t.get('topic', 'Task')}\n   Why for you: {t.get('justification', '')}" for i, t in enumerate(tasks)]) + "\n\nThis is my best guess at the complete journey. We can adjust this as we go based on what works for you."
            
            return {
                "success": True,
                "message": curriculum_text,
                "curriculum": curriculum_response
            }
        else:
            # Fallback: if we got a string, treat it as regular response
            self.conversation_history.append({
                "role": "assistant",
                "content": str(curriculum_response)
            })
            self.db.save_conversation_history(self.session_id, self.conversation_history)
            
            return {
                "success": True,
                "message": str(curriculum_response)
            }

    def _create_transition_message(self) -> str:
        """
        Create handoff to teaching phase.

        Returns:
            Transition message
        """
        rec = self.schema.teaching_recommendation

        if not rec.first_move:
            raise ValueError(f"TeachingRecommendation.first_move is required but was empty for topic: {rec.target_topic}")
        return rec.first_move

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

    def _generate_curriculum_justification(self, candidates: list) -> str:
        """
        Generate justification for why these teaching candidates form a good curriculum path.

        Args:
            candidates: List of TeachingCandidate objects in proposed order

        Returns:
            Justification text explaining the curriculum path
        """
        # Build candidate summaries
        candidates_text = "\n".join([
            f"{i+1}. {c.topic}\n   Gap: {c.identified_gap}\n   Focus: {c.focus_question}"
            for i, c in enumerate(candidates)
        ])

        prompt = f"""You're proposing a learning path for a user with this goal: "{self.schema.interview_state.proposed_goal or 'understanding key concepts'}"

USER CONTEXT:
- Background: {self.schema.user_profile.user_background[:200] if self.schema.user_profile.user_background else 'General learner'}
- Learning style: {self.schema.user_profile.pacing_preference.description if self.schema.user_profile.pacing_preference else 'adaptive'}

PROPOSED CURRICULUM PATH:
{candidates_text}

Generate a 2-3 sentence justification that:
1. Explains why these topics form a coherent learning path
2. Justifies why THIS ordering makes pedagogical sense (what builds on what)
3. Connects to the user's specific goals/gaps

Keep it conversational and personalized. Under 100 words.
Return just the justification text."""

        from src.config.model_config import get_model_name
        model_name = self.model_config.get("interviewer") or get_model_name("interviewer")

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.7,
            max_tokens=200
        )

        return response.strip()

    def end_session(self):
        """End the session and save final state."""
        final_topic = None
        if self.schema.teaching_recommendation.ready:
            final_topic = self.schema.teaching_recommendation.target_topic

        self.db.end_session(self.session_id, final_topic)
        print(f"[Orchestrator] Session ended. Total tokens used: {self.llm.get_total_tokens()}")
