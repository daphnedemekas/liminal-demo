"""Orchestrator for coordinating teaching curriculum conversation."""
from typing import Optional, Dict, Any, List
import uuid
import json
from pathlib import Path

from src.database.manager import DatabaseManager
from src.schema.teaching_schema import (
    TeachingSchema,
    TeachingCandidateInfo,
    CurriculumPlan,
    CurriculumStep,
    TeachingController,
    UnderstandingMarker,
    UnderstandingLevel,
    TeachingAction,
    CurriculumStepStatus,
    get_default_markers
)
from src.llm_client import LLMClient
from src.config import get_model_name


class TeachingOrchestrator:
    """
    Orchestrates the teaching curriculum conversation by:
    - Building/maintaining a curriculum plan
    - Selecting pedagogical moves each turn
    - Updating understanding markers
    - Persisting state to database
    """

    def __init__(
        self,
        user_id: str,
        goal_id: int,
        teaching_candidate_id: int,
        teaching_candidate: Dict[str, Any],
        goal_text: str,
        user_background: str = "",
        goal_conversation_history: Optional[List[Dict]] = None,
        db_path: str = "data/liminal.db",
        model_config: Optional[dict] = None,
        session_id: Optional[str] = None,
        conversation_history: Optional[List] = None,
        schema_state: Optional[Dict] = None
    ):
        """
        Initialize teaching orchestrator.

        Args:
            user_id: User identifier
            goal_id: ID of the learning goal
            teaching_candidate_id: ID of the teaching candidate
            teaching_candidate: Dict with topic, focus_question, identified_gap, etc.
            goal_text: The broader learning goal text
            user_background: User's background info
            goal_conversation_history: Conversation from goal discovery phase
            db_path: Path to SQLite database
            model_config: Optional model configuration override
            session_id: Optional existing session ID to resume
            conversation_history: Optional pre-loaded conversation history
            schema_state: Optional pre-loaded schema state
        """
        self.llm = LLMClient()
        self.model_config = model_config or {}
        self.db = DatabaseManager(db_path)
        
        self.user_id = user_id
        self.goal_id = goal_id
        self.teaching_candidate_id = teaching_candidate_id
        self.goal_text = goal_text
        self.user_background = user_background
        self.goal_conversation_history = goal_conversation_history or []
        
        # Resume or create session
        if session_id:
            self.session_id = session_id
            print(f"[TeachingOrchestrator] Resuming session: {session_id[:8]}...")
        else:
            self.session_id = str(uuid.uuid4())
            print(f"[TeachingOrchestrator] Creating new session: {self.session_id[:8]}...")
        
        # Initialize or restore schema
        if schema_state:
            print("[TeachingOrchestrator] Restoring schema state from database...")
            self.schema = TeachingSchema(**schema_state)
        else:
            self.schema = self._initialize_schema(teaching_candidate)
        
        # Initialize or restore conversation history
        self.conversation_history = conversation_history or []
        if conversation_history:
            print(f"[TeachingOrchestrator] Restored {len(conversation_history)} messages")

    def _initialize_schema(self, teaching_candidate: Dict[str, Any]) -> TeachingSchema:
        """Initialize new teaching schema."""
        candidate_info = TeachingCandidateInfo(
            id=self.teaching_candidate_id,
            topic=teaching_candidate.get("topic", ""),
            focus_question=teaching_candidate.get("focus_question", ""),
            identified_gap=teaching_candidate.get("identified_gap", ""),
            current_model_summary=teaching_candidate.get("current_model_summary"),
            stakes_summary=teaching_candidate.get("stakes_summary"),
            pedagogical_scope=teaching_candidate.get("pedagogical_scope", "10min"),
            angle=teaching_candidate.get("angle", "mechanism")
        )
        
        return TeachingSchema(
            session_id=self.session_id,
            user_id=self.user_id,
            goal_id=self.goal_id,
            teaching_candidate_id=self.teaching_candidate_id,
            teaching_candidate=candidate_info,
            curriculum_plan=CurriculumPlan(
                topic=candidate_info.topic,
                goal_text=self.goal_text
            ),
            understanding_markers=get_default_markers()
        )

    def start(self) -> str:
        """
        Start the teaching session by generating a curriculum plan and opening message.
        
        Returns:
            Opening message with curriculum overview
        """
        # Generate curriculum plan
        print("[TeachingOrchestrator] Generating curriculum plan...")
        self._generate_curriculum_plan()
        
        # Generate structured opening
        opening = self._generate_opening_message()
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": opening
        })
        
        # Save state
        self._save_state()
        
        return opening

    def _generate_curriculum_plan(self):
        """Generate the initial curriculum plan using LLM."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "plan_curriculum.txt"
        
        if not prompt_path.exists():
            print(f"[Warning] Curriculum prompt not found, using fallback")
            self._create_fallback_curriculum()
            return
        
        prompt_template = prompt_path.read_text()
        
        # Build goal conversation summary
        goal_conv_summary = ""
        if self.goal_conversation_history:
            relevant_messages = self.goal_conversation_history[-10:]  # Last 10 messages
            goal_conv_summary = "\n".join([
                f"{m['role'].upper()}: {m['content'][:200]}..." 
                if len(m['content']) > 200 else f"{m['role'].upper()}: {m['content']}"
                for m in relevant_messages
            ])
        else:
            goal_conv_summary = "(No prior conversation available)"
        
        prompt = prompt_template.format(
            goal_text=self.goal_text,
            topic=self.schema.teaching_candidate.topic,
            focus_question=self.schema.teaching_candidate.focus_question,
            identified_gap=self.schema.teaching_candidate.identified_gap,
            current_model_summary=self.schema.teaching_candidate.current_model_summary or "Unknown",
            stakes_summary=self.schema.teaching_candidate.stakes_summary or "Not specified",
            user_background=self.user_background,
            goal_conversation_summary=goal_conv_summary,
            turns_elapsed=0
        )
        
        model_name = get_model_name(self.model_config.get("ranker"), "ranker")
        
        try:
            result = self.llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.7,
                max_tokens=2000
            )
            
            if result:
                # Parse and validate curriculum
                self.schema.curriculum_plan = CurriculumPlan(**result)
                print(f"[TeachingOrchestrator] Created curriculum with {len(self.schema.curriculum_plan.steps)} steps")
            else:
                self._create_fallback_curriculum()
                
        except Exception as e:
            print(f"[TeachingOrchestrator] Error generating curriculum: {e}")
            self._create_fallback_curriculum()

    def _create_fallback_curriculum(self):
        """Create a simple fallback curriculum if LLM fails."""
        self.schema.curriculum_plan = CurriculumPlan(
            topic=self.schema.teaching_candidate.topic,
            goal_text=self.goal_text,
            total_steps=3,
            steps=[
                CurriculumStep(
                    id=1,
                    objective=f"Understand the basics of {self.schema.teaching_candidate.topic}",
                    explanation_approach="Start with concrete example",
                    quick_check="Can you explain the core concept in your own words?",
                    marker_targets=["explanation", "recall"],
                    prerequisites=[]
                ),
                CurriculumStep(
                    id=2,
                    objective="Explore how it works in practice",
                    explanation_approach="Walk through a real example step by step",
                    quick_check="What would happen if we changed this part?",
                    marker_targets=["application", "prediction"],
                    prerequisites=[1]
                ),
                CurriculumStep(
                    id=3,
                    objective="Connect to broader context and applications",
                    explanation_approach="Show connections to related concepts",
                    quick_check="Where else might you see this pattern?",
                    marker_targets=["transfer", "connection_making"],
                    prerequisites=[2]
                )
            ],
            current_step_id=1
        )

    def _generate_opening_message(self) -> str:
        """Generate the opening message with curriculum overview."""
        plan = self.schema.curriculum_plan
        candidate = self.schema.teaching_candidate
        
        # Build step overview
        steps_overview = "\n".join([
            f"{i+1}. **{step.objective}**"
            for i, step in enumerate(plan.steps[:5])  # Show up to 5 steps
        ])
        
        opening = f"""Great! Let's explore **{candidate.topic}** together.

Based on our conversation, here's what I'm thinking for our learning path:

{steps_overview}

We'll start with the fundamentals and build up from there. The goal is for you to really understand this - not just know the facts, but be able to reason about it and apply it.

{candidate.focus_question}

What's your current sense of this? Even a rough mental model or analogy helps me understand where to start."""

        return opening

    def process_user_message(self, user_message: str) -> str:
        """
        Process user message through the teaching pipeline.
        
        Args:
            user_message: User's message
            
        Returns:
            Teacher's response
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        self.schema.turns_elapsed += 1
        
        # Step 1: Determine next teaching action
        print("[TeachingOrchestrator] Determining next action...")
        self._update_controller(user_message)
        
        # Step 2: Assess understanding markers
        print("[TeachingOrchestrator] Assessing understanding...")
        self._assess_understanding(user_message)
        
        # Step 3: Check if curriculum needs adjustment
        print("[TeachingOrchestrator] Checking curriculum...")
        self._check_curriculum_adaptation()
        
        # Step 4: Generate teacher response
        print("[TeachingOrchestrator] Generating response...")
        response = self._generate_teacher_response(user_message)
        
        # Step 5: Update curriculum progress if appropriate
        self._update_progress()
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        # Save state
        self._save_state()
        
        return response

    def _update_controller(self, user_message: str):
        """Update controller state based on conversation."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "generate_teaching_controller.txt"
        
        if not prompt_path.exists():
            # Fallback controller logic
            self._fallback_controller_update(user_message)
            return
        
        prompt_template = prompt_path.read_text()
        
        # Build teaching state summary
        current_step = self._get_current_step()
        teaching_state = {
            "topic": self.schema.teaching_candidate.topic,
            "current_step": current_step.objective if current_step else "No step active",
            "turns_elapsed": self.schema.turns_elapsed,
            "curriculum_progress": f"{len(self.schema.curriculum_plan.completed_step_ids)}/{self.schema.curriculum_plan.total_steps}",
            "recent_markers": self._get_recent_marker_updates()
        }
        
        # Format conversation
        recent_conv = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        conv_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_conv])
        
        prompt = prompt_template.format(
            teaching_state=json.dumps(teaching_state, indent=2),
            conversation=conv_text,
            user_message=user_message
        )
        
        model_name = get_model_name(self.model_config.get("ranker"), "ranker")
        
        try:
            result = self.llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.5,
                max_tokens=800
            )
            
            if result:
                self.schema.controller = TeachingController(
                    next_action=TeachingAction(result.get("next_action", "explain")),
                    action_rationale=result.get("action_rationale", ""),
                    focus_content=result.get("focus_content", ""),
                    target_markers=result.get("target_markers", []),
                    user_question_pending=result.get("user_question_pending", False),
                    user_question=result.get("user_question"),
                    confusion_detected=result.get("confusion_detected", False),
                    prerequisite_gap_detected=result.get("prerequisite_gap_detected", False),
                    pacing_adjustment=result.get("pacing_adjustment")
                )
                print(f"[TeachingOrchestrator] Controller: {self.schema.controller.next_action}")
            else:
                self._fallback_controller_update(user_message)
                
        except Exception as e:
            print(f"[TeachingOrchestrator] Controller error: {e}")
            self._fallback_controller_update(user_message)

    def _fallback_controller_update(self, user_message: str):
        """Simple fallback controller logic."""
        # Check for question
        if "?" in user_message:
            self.schema.controller = TeachingController(
                next_action=TeachingAction.ANSWER_QUESTION,
                action_rationale="User asked a question",
                focus_content=user_message,
                user_question_pending=True,
                user_question=user_message
            )
        # Check for confusion signals
        elif any(phrase in user_message.lower() for phrase in ["don't understand", "confused", "what?", "huh"]):
            self.schema.controller = TeachingController(
                next_action=TeachingAction.PROVIDE_EXAMPLE,
                action_rationale="User seems confused",
                focus_content="Clarify with concrete example",
                confusion_detected=True
            )
        else:
            # Default: continue explaining
            self.schema.controller = TeachingController(
                next_action=TeachingAction.EXPLAIN,
                action_rationale="Continue teaching",
                focus_content=self._get_current_step().objective if self._get_current_step() else "Continue"
            )

    def _assess_understanding(self, user_message: str):
        """Assess understanding markers based on conversation."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "assess_understanding_markers_delta.txt"
        
        if not prompt_path.exists():
            return  # Skip if prompt not available
        
        prompt_template = prompt_path.read_text()
        
        current_step = self._get_current_step()
        markers_summary = [
            {"id": m.id, "name": m.name, "level": m.level, "evidence": m.evidence[-2:]}
            for m in self.schema.understanding_markers
        ]
        
        recent_conv = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        conv_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_conv])
        
        prompt = prompt_template.format(
            understanding_markers=json.dumps(markers_summary, indent=2),
            topic=self.schema.teaching_candidate.topic,
            current_step=current_step.id if current_step else 0,
            current_step_objective=current_step.objective if current_step else "N/A",
            conversation=conv_text,
            user_message=user_message
        )
        
        model_name = get_model_name(self.model_config.get("ranker"), "ranker")
        
        try:
            result = self.llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.3,
                max_tokens=1000
            )
            
            if result and "marker_updates" in result:
                for update in result["marker_updates"]:
                    marker_id = update.get("id")
                    for marker in self.schema.understanding_markers:
                        if marker.id == marker_id:
                            marker.level = UnderstandingLevel(update.get("new_level", marker.level))
                            marker.evidence.extend(update.get("evidence", []))
                            marker.notes = update.get("notes", marker.notes)
                            marker.last_assessed_turn = self.schema.turns_elapsed
                            break
                
                # Update narrative summary
                if "overall_assessment" in result:
                    self.schema.narrative_summary = result["overall_assessment"]
                    
        except Exception as e:
            print(f"[TeachingOrchestrator] Assessment error: {e}")

    def _check_curriculum_adaptation(self):
        """Check if curriculum needs adjustment."""
        # Skip frequent adaptation checks
        if self.schema.turns_elapsed < 3:
            return
        
        if self.schema.curriculum_plan.adaptations_made > 3:
            return  # Avoid over-adapting
        
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "update_curriculum_plan_delta.txt"
        
        if not prompt_path.exists():
            return
        
        # Only check every few turns or when confusion detected
        if not self.schema.controller.confusion_detected and self.schema.turns_elapsed % 4 != 0:
            return
        
        prompt_template = prompt_path.read_text()
        
        recent_conv = self.conversation_history[-4:] if len(self.conversation_history) > 4 else self.conversation_history
        conv_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_conv])
        
        markers_summary = [
            {"id": m.id, "level": m.level}
            for m in self.schema.understanding_markers
            if m.last_assessed_turn > 0
        ]
        
        prompt = prompt_template.format(
            curriculum_plan=self.schema.curriculum_plan.model_dump_json(indent=2),
            understanding_markers=json.dumps(markers_summary, indent=2),
            conversation=conv_text,
            controller_state=self.schema.controller.model_dump_json(indent=2)
        )
        
        model_name = get_model_name(self.model_config.get("ranker"), "ranker")
        
        try:
            result = self.llm.chat_with_json(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.5,
                max_tokens=1500
            )
            
            if result and result.get("should_adapt"):
                self._apply_curriculum_adaptation(result)
                
        except Exception as e:
            print(f"[TeachingOrchestrator] Curriculum adaptation error: {e}")

    def _apply_curriculum_adaptation(self, adaptation: Dict):
        """Apply curriculum adaptation from LLM result."""
        adaptation_type = adaptation.get("adaptation_type", "no_change")
        changes = adaptation.get("changes", {})
        
        if adaptation_type == "no_change":
            return
        
        plan = self.schema.curriculum_plan
        
        if adaptation_type == "insert_step" and "new_step" in changes:
            new_step = CurriculumStep(**changes["new_step"])
            position = changes.get("position", len(plan.steps))
            plan.steps.insert(position, new_step)
            plan.total_steps = len(plan.steps)
            
        elif adaptation_type == "remove_step" and "step_id_to_remove" in changes:
            step_id = changes["step_id_to_remove"]
            plan.steps = [s for s in plan.steps if s.id != step_id]
            plan.total_steps = len(plan.steps)
            
        elif adaptation_type == "modify_step" and "step_id" in changes:
            step_id = changes["step_id"]
            field = changes.get("field")
            new_value = changes.get("new_value")
            if field and new_value:
                for step in plan.steps:
                    if step.id == step_id:
                        setattr(step, field, new_value)
                        break
        
        # Record adaptation
        plan.adaptations_made += 1
        plan.adaptation_history.append(adaptation.get("adaptation_note", "Adaptation made"))
        plan.last_modified_turn = self.schema.turns_elapsed
        
        print(f"[TeachingOrchestrator] Applied {adaptation_type} adaptation")

    def _generate_teacher_response(self, user_message: str) -> str:
        """Generate the teacher's response."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "teacher_response.txt"
        
        if not prompt_path.exists():
            return self._fallback_response(user_message)
        
        prompt_template = prompt_path.read_text()
        
        current_step = self._get_current_step()
        ctrl = self.schema.controller
        
        recent_conv = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        conv_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_conv])
        
        prompt = prompt_template.format(
            topic=self.schema.teaching_candidate.topic,
            goal_text=self.goal_text,
            current_step_objective=current_step.objective if current_step else "Building understanding",
            focus_question=self.schema.teaching_candidate.focus_question,
            identified_gap=self.schema.teaching_candidate.identified_gap,
            next_action=ctrl.next_action,
            focus_content=ctrl.focus_content,
            target_markers=", ".join(ctrl.target_markers) if ctrl.target_markers else "general understanding",
            action_rationale=ctrl.action_rationale,
            user_background=self.user_background,
            conversation=conv_text,
            user_message=user_message
        )
        
        model_name = get_model_name(self.model_config.get("interviewer"), "interviewer")
        
        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.7,
                max_tokens=1000
            )
            return response
            
        except Exception as e:
            print(f"[TeachingOrchestrator] Response generation error: {e}")
            return self._fallback_response(user_message)

    def _fallback_response(self, user_message: str) -> str:
        """Generate fallback response if LLM fails."""
        candidate = self.schema.teaching_candidate
        
        if "?" in user_message:
            return f"Good question! Let me think about that in the context of {candidate.topic}. Can you tell me more about what specifically is unclear?"
        else:
            return f"That's helpful context. Let me continue explaining {candidate.topic}. What aspect would you like me to focus on next?"

    def _update_progress(self):
        """Update curriculum progress based on understanding markers."""
        current_step = self._get_current_step()
        if not current_step:
            return
        
        current_step.turns_spent += 1
        
        # Check if current step's target markers are developing/strong
        target_marker_ids = current_step.marker_targets
        markers_ok = 0
        
        for marker in self.schema.understanding_markers:
            if marker.id in target_marker_ids:
                if marker.level in [UnderstandingLevel.DEVELOPING, UnderstandingLevel.STRONG]:
                    markers_ok += 1
        
        # If most target markers are developing+ and spent enough turns, complete step
        if target_marker_ids:
            completion_ratio = markers_ok / len(target_marker_ids)
            if completion_ratio >= 0.5 and current_step.turns_spent >= 2:
                current_step.status = CurriculumStepStatus.COMPLETED
                self.schema.curriculum_plan.completed_step_ids.append(current_step.id)
                
                # Move to next step
                self._advance_to_next_step()
                print(f"[TeachingOrchestrator] Completed step {current_step.id}, advancing...")

    def _advance_to_next_step(self):
        """Advance to the next curriculum step."""
        plan = self.schema.curriculum_plan
        current_idx = self.schema.current_step_index
        
        if current_idx < len(plan.steps) - 1:
            self.schema.current_step_index += 1
            plan.current_step_id = plan.steps[self.schema.current_step_index].id
            plan.steps[self.schema.current_step_index].status = CurriculumStepStatus.IN_PROGRESS
        else:
            # All steps completed
            self.schema.phase_complete = True
            print("[TeachingOrchestrator] All curriculum steps completed!")

    def _get_current_step(self) -> Optional[CurriculumStep]:
        """Get the current curriculum step."""
        if self.schema.current_step_index < len(self.schema.curriculum_plan.steps):
            return self.schema.curriculum_plan.steps[self.schema.current_step_index]
        return None

    def _get_recent_marker_updates(self) -> List[Dict]:
        """Get recently updated markers."""
        recent = []
        for marker in self.schema.understanding_markers:
            if marker.last_assessed_turn >= self.schema.turns_elapsed - 2:
                recent.append({
                    "id": marker.id,
                    "level": marker.level,
                    "evidence": marker.evidence[-1] if marker.evidence else None
                })
        return recent

    def _save_state(self):
        """Save schema and conversation history to database."""
        print("[TeachingOrchestrator] Saving state to database...")
        self.db.save_session_state(self.session_id, self.schema.model_dump())
        self.db.save_conversation_history(self.session_id, self.conversation_history)

    def get_schema(self) -> Dict:
        """Return current schema for debugging/display."""
        return self.schema.model_dump()

    def is_complete(self) -> bool:
        """Check if teaching phase is complete."""
        return self.schema.phase_complete

