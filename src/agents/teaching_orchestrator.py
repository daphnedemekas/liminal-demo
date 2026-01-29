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
    TeachingPhase,
    CurriculumStepStatus,
    get_default_markers
)
from src.llm_client import LLMClient
from src.config import get_model_name
from src.prompt.assembly import assemble_prompt
from src.prompt.gather import gather_conversation, gather_teaching_context
from src.prompt_loader import PromptLoader


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
        existing_teaching_candidates: Optional[List[Dict[str, Any]]] = None,
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
            existing_teaching_candidates: List of other teaching candidates for this goal (for sequential awareness)
            db_path: Path to SQLite database
            model_config: Optional model configuration override
            session_id: Optional existing session ID to resume
            conversation_history: Optional pre-loaded conversation history
            schema_state: Optional pre-loaded schema state
        """
        self.llm = LLMClient()
        self.model_config = model_config or {}
        self.db = DatabaseManager(db_path=db_path)
        self.prompt_loader = PromptLoader()
        
        # Get repo root for prompt assembly
        project_root = Path(__file__).parent.parent.parent
        self.repo_root = project_root
        
        self.user_id = user_id
        self.goal_id = goal_id
        self.teaching_candidate_id = teaching_candidate_id
        self.goal_text = goal_text
        self.user_background = user_background
        self.goal_conversation_history = goal_conversation_history or []
        self.existing_teaching_candidates = existing_teaching_candidates or []
        
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

    def _format_teaching_candidates_context(self) -> str:
        """
        Format existing teaching candidates into context string for prompts.
        
        Returns:
            Formatted string describing other teaching candidates for this goal
        """
        if not self.existing_teaching_candidates:
            return "No other teaching topics have been covered yet for this goal."
        
        context_parts = []
        context_parts.append(f"You are aware of {len(self.existing_teaching_candidates)} other teaching topic(s) that have been or are being covered for this goal:")
        
        for idx, candidate in enumerate(self.existing_teaching_candidates, 1):
            topic = candidate.get("topic", "Unknown topic")
            status = candidate.get("status", "unknown")
            identified_gap = candidate.get("identified_gap", "")
            
            status_desc = {
                "completed": "completed",
                "in_progress": "currently being taught",
                "available": "available to start",
                "locked": "locked (prerequisites not met)"
            }.get(status, status)
            
            gap_text = f" (Gap: {identified_gap})" if identified_gap else ""
            context_parts.append(f"{idx}. {topic} - {status_desc}{gap_text}")
        
        context_parts.append("\nWhen teaching the current topic, structure your delivery with awareness of these other topics. Reference how they connect or build on each other when relevant.")
        
        return "\n".join(context_parts)

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
            angle=teaching_candidate.get("angle", "mechanism"),
            source_material=teaching_candidate.get("source_material"),
            source_citations=teaching_candidate.get("source_citations")
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

    def start(self) -> dict:
        """
        Start the teaching session with assessment phase.
        
        Returns:
            Dict with opening message and metadata
        """
        # Start in ASSESSMENT phase - don't generate curriculum yet
        self.schema.teaching_phase = TeachingPhase.ASSESSMENT
        print(f"[TeachingOrchestrator] Starting in ASSESSMENT phase for topic: {self.schema.teaching_candidate.topic}")
        
        # Generate assessment opening question
        opening = self._generate_assessment_opening()
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant",
            "content": opening
        })
        
        # Save state
        self._save_state()
        
        return {
            "message": opening,
            "phase": self.schema.teaching_phase.value,
            "type": "assessment_question"
        }
    
    def _generate_assessment_opening(self) -> str:
        """Generate opening question to assess user's prior knowledge for this specific topic."""
        candidate = self.schema.teaching_candidate
        
        prompt = f"""You are starting a teaching session on "{candidate.topic}".

CONTEXT:
- Overall Goal: {self.goal_text}
- This Topic: {candidate.topic}
- Identified Gap: {candidate.identified_gap}
- Focus Question: {candidate.focus_question}
- User Background: {self.user_background}

TASK: Ask a single probing question to understand what they ALREADY know about this specific topic. The question should reveal their mental model, not just yes/no understanding.

IMPORTANT:
- Do NOT include any welcome message, greeting, or preamble. Jump straight to the question.
- Don't ask "what do you know about X?" directly. Instead:
  - Ask them to explain a related concept
  - Present a scenario and ask how they'd think about it
  - Ask about their intuition or mental model
  - Reference something from the goal conversation to build on

Keep your response under 60 words. Just the question, nothing else.

Return just the message text, no JSON."""

        model_name = self.model_config.get("interviewer") or get_model_name("interviewer")
        
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.8,
            max_tokens=300
        )
        
        return response.strip()

    def _generate_curriculum_plan(self):
        """Generate the initial curriculum plan using LLM. Raises errors on failure."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "plan_curriculum.txt"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Curriculum prompt not found at: {prompt_path}")
        
        # Build goal conversation summary
        goal_conv_summary = ""
        if self.goal_conversation_history:
            relevant_messages = self.goal_conversation_history[-10:]  # Last 10 messages
            result = gather_conversation(relevant_messages, max_messages=10, max_chars=2000)
            goal_conv_summary = result if result else "(No prior conversation available)"
        else:
            goal_conv_summary = "(No prior conversation available)"
        
        # Format existing teaching candidates context
        existing_candidates_context = self._format_teaching_candidates_context()
        
        # Build teaching context
        teaching_context = {
            "goal_text": self.goal_text,
            "focus_question": self.schema.teaching_candidate.focus_question,
            "identified_gap": self.schema.teaching_candidate.identified_gap,
            "current_model_summary": self.schema.teaching_candidate.current_model_summary or "Unknown",
            "stakes_summary": self.schema.teaching_candidate.stakes_summary or "Not specified",
            "goal_conversation_summary": goal_conv_summary,
            "existing_teaching_candidates": existing_candidates_context,
            "assessment_concepts_known": ", ".join(self.schema.assessment_concepts_known) if self.schema.assessment_concepts_known else "Still assessing",
            "assessment_concepts_unclear": ", ".join(self.schema.assessment_concepts_unclear) if self.schema.assessment_concepts_unclear else "Still assessing",
            "assessment_confidence": f"{self.schema.assessment_confidence:.2f}",
            "source_material": self.schema.teaching_candidate.source_material or "(No reference material provided)",
            "turns_elapsed": 0
        }
        
        # Use assemble_prompt to build prompt with context
        prompt, dropped = assemble_prompt(
            step_name="plan_curriculum",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            schema_state=self.schema,
            user_background=self.user_background,
            teaching_context=teaching_context,
            task="teaching",
        )
        
        # Use model override if provided, otherwise fall back to config
        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        
        print(f"[TeachingOrchestrator] Generating curriculum for topic: {self.schema.teaching_candidate.topic}")
        print(f"[TeachingOrchestrator] Using model: {model_name}")
        
        result = self.llm.chat_with_json(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.7,
            max_tokens=2000
        )
        
        if not result:
            raise ValueError(f"LLM returned empty result for curriculum generation. Model: {model_name}")
        
        # Parse and validate curriculum
        self.schema.curriculum_plan = CurriculumPlan(**result)
        print(f"[TeachingOrchestrator] Created curriculum with {len(self.schema.curriculum_plan.steps)} steps:")
        for i, step in enumerate(self.schema.curriculum_plan.steps):
            print(f"  Step {i+1}: {step.objective}")

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

    def process_user_message(self, user_message: str) -> dict:
        """
        Process user message through the teaching pipeline.
        
        Args:
            user_message: User's message
            
        Returns:
            Dict with response and metadata (phase, type, etc.)
        """
        # Check for special commands
        if user_message == "__ACCEPT_CURRICULUM__":
            return self._handle_accept_curriculum()
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Save user message to database IMMEDIATELY so it persists even if user refreshes
        print("[DB] Saving user message to conversation history immediately...")
        self.db.save_conversation_history(self.session_id, self.conversation_history)
        
        self.schema.turns_elapsed += 1
        current_phase = self.schema.teaching_phase
        print(f"[TeachingOrchestrator] Processing message in phase: {current_phase}")
        
        # Handle based on current phase
        if current_phase == TeachingPhase.ASSESSMENT:
            return self._process_assessment_phase(user_message)
        elif current_phase == TeachingPhase.CURRICULUM_PROPOSAL:
            return self._process_proposal_phase(user_message)
        elif current_phase == TeachingPhase.NEGOTIATION:
            return self._process_negotiation_phase(user_message)
        else:  # TEACHING phase
            return self._process_teaching_phase(user_message)
    
    def _process_assessment_phase(self, user_message: str) -> dict:
        """Process message during assessment phase."""
        print("[TeachingOrchestrator] Assessment phase - analyzing user's knowledge...")
        
        # Analyze user's response to update assessment
        self._analyze_assessment_response(user_message)
        
        # Check if we have enough confidence to propose curriculum
        # Usually after 2-3 turns of assessment
        if self.schema.assessment_confidence >= 0.6 or self.schema.turns_elapsed >= 3:
            print(f"[TeachingOrchestrator] Assessment complete (confidence: {self.schema.assessment_confidence:.2f})")
            return self._transition_to_curriculum_proposal()
        else:
            # Generate follow-up assessment question
            response = self._generate_assessment_followup(user_message)
            self.conversation_history.append({"role": "assistant", "content": response})
            self._save_state()
            return {
                "message": response,
                "phase": "assessment",
                "type": "assessment_question"
            }
    
    def _analyze_assessment_response(self, user_message: str):
        """Analyze user's response to extract knowledge level."""
        prompt = f"""Analyze this user response to understand their prior knowledge about "{self.schema.teaching_candidate.topic}".

USER'S RESPONSE:
{user_message}

CONTEXT:
- Topic: {self.schema.teaching_candidate.topic}
- Identified Gap: {self.schema.teaching_candidate.identified_gap}

Return JSON:
{{
  "concepts_demonstrated": ["concept1", "concept2"],  // Concepts they clearly understand
  "concepts_unclear": ["concept3"],  // Concepts they're confused about or missing
  "assessment_confidence": 0.7,  // 0-1, how confident are we about their level?
  "overall_level": "beginner|intermediate|advanced",
  "learning_style_hints": ["prefers analogies", "wants math details"]
}}

Return ONLY valid JSON."""

        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        result = self.llm.chat_with_json(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.3,
            max_tokens=500
        )
        
        if result:
            # Update schema with assessment results
            for concept in result.get("concepts_demonstrated", []):
                if concept and concept not in self.schema.assessment_concepts_known:
                    self.schema.assessment_concepts_known.append(concept)
            for concept in result.get("concepts_unclear", []):
                if concept and concept not in self.schema.assessment_concepts_unclear:
                    self.schema.assessment_concepts_unclear.append(concept)
            
            # Update confidence (average with existing)
            new_confidence = result.get("assessment_confidence", 0.5)
            self.schema.assessment_confidence = max(self.schema.assessment_confidence, new_confidence)
            print(f"[Assessment] Updated confidence: {self.schema.assessment_confidence:.2f}")
    
    def _generate_assessment_followup(self, user_message: str) -> str:
        """Generate follow-up question to continue assessment."""
        prompt = f"""You are assessing a learner's knowledge about "{self.schema.teaching_candidate.topic}".

CONVERSATION SO FAR:
{self._format_recent_conversation()}

WHAT WE'VE LEARNED ABOUT THEM:
- Concepts they know: {', '.join(self.schema.assessment_concepts_known) or 'Still assessing'}
- Concepts unclear: {', '.join(self.schema.assessment_concepts_unclear) or 'Still assessing'}
- Assessment confidence: {self.schema.assessment_confidence:.2f}

TASK: Generate a follow-up question that:
1. Probes deeper into their understanding
2. Explores a different angle than previous questions
3. Helps us understand their mental model better
4. Is conversational, not quiz-like

Keep it under 80 words. Be warm and curious.
Return just the message text."""

        model_name = self.model_config.get("interviewer") or get_model_name("interviewer")
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.8,
            max_tokens=200
        )
        return response.strip()
    
    def _transition_to_curriculum_proposal(self) -> dict:
        """Generate curriculum and propose it to user."""
        print("[TeachingOrchestrator] Transitioning to CURRICULUM_PROPOSAL phase...")
        self.schema.teaching_phase = TeachingPhase.CURRICULUM_PROPOSAL
        
        # Generate curriculum using assessment data
        self._generate_curriculum_plan()
        
        # Generate proposal message with justifications
        response = self._generate_curriculum_proposal_message()
        
        self.conversation_history.append({"role": "assistant", "content": response})
        self._save_state()
        
        return {
            "message": response,
            "phase": "curriculum_proposal",
            "type": "curriculum_proposed",  # This triggers Accept/Modify buttons in UI
            "curriculum_plan": {
                "steps": [{"objective": s.objective, "why_for_you": s.why_for_you} for s in self.schema.curriculum_plan.steps]
            }
        }
    
    def _generate_curriculum_proposal_message(self) -> str:
        """Generate message proposing the curriculum with justifications."""
        plan = self.schema.curriculum_plan
        candidate = self.schema.teaching_candidate
        
        # Build steps with justifications
        steps_text = ""
        for i, step in enumerate(plan.steps[:5]):  # Show up to 5 steps
            why = step.why_for_you or "This builds on what you already know."
            steps_text += f"\n{i+1}. **{step.objective}**\n   *Why this for you:* {why}\n"
        
        assessment_summary = ""
        if self.schema.assessment_concepts_known:
            assessment_summary = f"\n\nFrom our conversation, I can see you already understand: {', '.join(self.schema.assessment_concepts_known[:3])}."
        if self.schema.assessment_concepts_unclear:
            assessment_summary += f" We'll focus on clarifying: {', '.join(self.schema.assessment_concepts_unclear[:3])}."
        
        message = f"""Based on what you've shared, I've designed a learning path for **{candidate.topic}**:{assessment_summary}

**Proposed Curriculum:**
{steps_text}

Does this learning path work for you? We can adjust the focus, add steps, or skip things you already know."""
        
        return message
    
    def _handle_accept_curriculum(self) -> dict:
        """Handle user accepting the proposed curriculum."""
        print("[TeachingOrchestrator] User accepted curriculum - transitioning to TEACHING phase")
        self.schema.curriculum_accepted = True
        self.schema.teaching_phase = TeachingPhase.TEACHING

        # Mark first step as in progress
        if len(self.schema.curriculum_plan.steps) > 0:
            self.schema.curriculum_plan.steps[0].status = CurriculumStepStatus.IN_PROGRESS
            self.schema.curriculum_plan.current_step_id = self.schema.curriculum_plan.steps[0].id

        # Generate first teaching message
        response = self._generate_first_teaching_message()

        self.conversation_history.append({"role": "assistant", "content": response})
        self._save_state()

        return {
            "message": response,
            "phase": "teaching",
            "type": "curriculum_accepted",
            "curriculum_progress": {
                "current_step": self.schema.current_step_index,
                "total_steps": len(self.schema.curriculum_plan.steps),
                "completed_steps": len(self.schema.curriculum_plan.completed_step_ids)
            }
        }
    
    def _generate_first_teaching_message(self) -> str:
        """Generate the first actual teaching message after curriculum acceptance."""
        current_step = self._get_current_step()
        if not current_step:
            return "Let's begin! What would you like to start with?"
        
        prompt = f"""You're starting to teach "{self.schema.teaching_candidate.topic}".

FIRST CURRICULUM STEP:
- Objective: {current_step.objective}
- Approach: {current_step.explanation_approach}

USER'S BACKGROUND:
- They know: {', '.join(self.schema.assessment_concepts_known) or 'basics'}
- They need clarity on: {', '.join(self.schema.assessment_concepts_unclear) or 'core concepts'}

Generate a teaching message that:
1. Acknowledges they're ready to begin
2. Introduces the first concept clearly
3. Uses an analogy or concrete example
4. Ends with an engagement hook (question or thought prompt)

Keep it focused and under 150 words. No fluff.
Return just the teaching message."""

        model_name = self.model_config.get("interviewer") or get_model_name("interviewer")
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.7,
            max_tokens=400
        )
        return response.strip()
    
    def _process_proposal_phase(self, user_message: str) -> dict:
        """Process message during curriculum proposal (user giving feedback)."""
        # User is providing feedback on curriculum - transition to negotiation
        self.schema.teaching_phase = TeachingPhase.NEGOTIATION
        return self._process_negotiation_phase(user_message)
    
    def _process_negotiation_phase(self, user_message: str) -> dict:
        """Process user's curriculum modification request."""
        print("[TeachingOrchestrator] Negotiation phase - adjusting curriculum...")
        
        # Analyze modification request and adjust curriculum
        self._adjust_curriculum_based_on_feedback(user_message)
        
        # Re-propose
        response = self._generate_curriculum_proposal_message()
        
        self.conversation_history.append({"role": "assistant", "content": response})
        self._save_state()
        
        return {
            "message": response,
            "phase": "negotiation",
            "type": "curriculum_proposed"
        }
    
    def _adjust_curriculum_based_on_feedback(self, user_message: str):
        """Adjust curriculum based on user's modification request."""
        prompt = f"""User wants to modify this curriculum for "{self.schema.teaching_candidate.topic}":

CURRENT CURRICULUM:
{[{"id": s.id, "objective": s.objective} for s in self.schema.curriculum_plan.steps]}

USER'S FEEDBACK:
{user_message}

Suggest modifications. Return JSON:
{{
  "action": "add|remove|modify|reorder",
  "step_ids_affected": [1, 2],
  "new_objectives": ["New objective 1"],  // Only if adding/modifying
  "reasoning": "Brief explanation"
}}

Return ONLY valid JSON."""

        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        result = self.llm.chat_with_json(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.5,
            max_tokens=500
        )

        if result:
            action = result.get('action', 'unknown')
            reasoning = result.get('reasoning', 'User requested modification')

            # Record the modification
            self.schema.curriculum_plan.adaptation_history.append(
                f"User requested: {user_message[:100]}. Action: {action}. {reasoning}"
            )

            # Actually apply the modifications
            if action != "no_change":
                adaptation_for_apply = {
                    "adaptation_type": action,
                    "changes": result,
                    "adaptation_note": reasoning
                }
                self._apply_curriculum_adaptation(adaptation_for_apply)
                print(f"[TeachingOrchestrator] Applied {action} modification based on user feedback")
    
    def _process_teaching_phase(self, user_message: str) -> dict:
        """Process message during active teaching phase."""
        # Original teaching logic
        print("[TeachingOrchestrator] Teaching phase - processing...")
        
        # Step 1: Determine next teaching action
        self._update_controller(user_message)
        
        # Step 2: Assess understanding markers
        self._assess_understanding(user_message)
        
        # Step 3: Check if curriculum needs adjustment
        self._check_curriculum_adaptation()
        
        # Step 4: Generate teacher response
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
        
        return {
            "message": response,
            "phase": "teaching",
            "type": "teaching_message",
            "curriculum_progress": {
                "current_step": self.schema.current_step_index,
                "total_steps": len(self.schema.curriculum_plan.steps),
                "completed_steps": len(self.schema.curriculum_plan.completed_step_ids)
            }
        }
    
    def _format_recent_conversation(self) -> str:
        """Format recent conversation for prompts."""
        recent = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        return "\n".join([f"{m['role'].upper()}: {m['content'][:200]}..." if len(m['content']) > 200 else f"{m['role'].upper()}: {m['content']}" for m in recent])

    def _update_controller(self, user_message: str):
        """Update controller state based on conversation. Raises errors on failure."""
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
        
        # Format existing teaching candidates context
        existing_candidates_context = self._format_teaching_candidates_context()
        
        # Build teaching context
        teaching_context = {
            "teaching_state": teaching_state,
            "user_message": user_message,
            "existing_teaching_candidates": existing_candidates_context
        }
        
        # Use assemble_prompt to build prompt with context
        prompt, dropped = assemble_prompt(
            step_name="generate_teaching_controller",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            conversation_history=recent_conv,
            schema_state=self.schema,
            teaching_context=teaching_context,
            task="teaching",
        )
        
        # Use model override if provided, otherwise fall back to config
        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        
        result = self.llm.chat_with_json(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.5,
            max_tokens=800
        )
        
        if not result:
            raise ValueError(f"LLM returned empty result for controller update. Model: {model_name}")
        
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

    def _assess_understanding(self, user_message: str):
        """Assess understanding markers based on conversation."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "assess_understanding_markers_delta.txt"
        
        if not prompt_path.exists():
            return  # Skip if prompt not available
        
        current_step = self._get_current_step()
        markers_summary = [
            {"id": m.id, "name": m.name, "level": m.level, "evidence": m.evidence[-2:]}
            for m in self.schema.understanding_markers
        ]
        
        recent_conv = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        
        # Build teaching context
        teaching_context = {
            "understanding_markers": markers_summary,
            "current_step": current_step.id if current_step else 0,
            "current_step_objective": current_step.objective if current_step else "N/A",
            "user_message": user_message
        }
        
        # Use assemble_prompt to build prompt with context
        prompt, dropped = assemble_prompt(
            step_name="assess_understanding_markers_delta",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            conversation_history=recent_conv,
            schema_state=self.schema,
            teaching_context=teaching_context,
            task="teaching",
        )
        
        # Use model override if provided, otherwise fall back to config
        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        
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
        
        recent_conv = self.conversation_history[-4:] if len(self.conversation_history) > 4 else self.conversation_history
        
        markers_summary = [
            {"id": m.id, "level": m.level}
            for m in self.schema.understanding_markers
            if m.last_assessed_turn > 0
        ]
        
        # Build teaching context
        teaching_context = {
            "curriculum_plan": self.schema.curriculum_plan.model_dump(),
            "understanding_markers": markers_summary,
            "controller_state": self.schema.controller.model_dump()
        }
        
        # Use assemble_prompt to build prompt with context
        prompt, dropped = assemble_prompt(
            step_name="update_curriculum_plan_delta",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            conversation_history=recent_conv,
            schema_state=self.schema,
            teaching_context=teaching_context,
            task="teaching",
        )
        
        # Use model override if provided, otherwise fall back to config
        model_name = self.model_config.get("ranker") or get_model_name("ranker")
        
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
        """Generate the teacher's response. Raises errors on failure."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "teaching" / "teacher_response.txt"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Teacher response prompt not found at: {prompt_path}")
        
        current_step = self._get_current_step()
        ctrl = self.schema.controller
        
        recent_conv = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        
        # Build teaching context
        teaching_context = {
            "goal_text": self.goal_text,
            "current_step_objective": current_step.objective if current_step else "Building understanding",
            "focus_question": self.schema.teaching_candidate.focus_question,
            "identified_gap": self.schema.teaching_candidate.identified_gap,
            "next_action": str(ctrl.next_action),
            "focus_content": ctrl.focus_content,
            "target_markers": ", ".join(ctrl.target_markers) if ctrl.target_markers else "general understanding",
            "action_rationale": ctrl.action_rationale,
            "source_material": self.schema.teaching_candidate.source_material or "(No reference material provided)",
            "user_message": user_message,
            "existing_teaching_candidates": self._format_teaching_candidates_context()
        }
        
        # Use assemble_prompt to build prompt with context
        prompt, dropped = assemble_prompt(
            step_name="teacher_response",
            prompt_loader=self.prompt_loader,
            repo_root=self.repo_root,
            conversation_history=recent_conv,
            schema_state=self.schema,
            user_background=self.user_background,
            teaching_context=teaching_context,
            task="teaching",
        )
        
        # Use model override if provided, otherwise fall back to config
        model_name = self.model_config.get("interviewer") or get_model_name("interviewer")
        
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.7,
            max_tokens=1000
        )
        
        if not response:
            raise ValueError(f"LLM returned empty response for teacher. Model: {model_name}")
        
        return response

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


