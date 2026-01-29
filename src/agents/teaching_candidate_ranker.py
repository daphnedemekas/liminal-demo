"""Teaching candidate ranker for Phase 2: finding a teachable topic."""
from typing import Dict, Any, List, Tuple
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.agents.ranker_base import RankerAgentBase
from src.schema.full_schema import (
    DiscoverySchema,
    UserProfile,
    ConversationalTheme,
    TeachingCandidate,
    Controller,
    TeachingRecommendation,
    PriorKnowledgeAssessment,
    AssessmentEvidence
)


class TeachingCandidateRanker(RankerAgentBase):
    """
    Ranker for Phase 2: Finding a teachable topic given a learning goal.

    Used after a goal has been identified. This ranker:
    - Updates teaching_candidates (NOT goal_candidates)
    - Tracks teaching readiness scores
    - Signals when ready to teach (readiness >= 0.65-0.7)
    - Focuses on finding specific, teachable first steps

    Dimension priorities (Phase 2):
    - High: uncertainty_tolerance (0.9), pacing_preference (0.8)
    - Medium: entry_mode (0.4 - for framing the teaching)
    - Low: curiosity_type (0.2), motivation_profile (0.2), interest_phase (0.2)
    """

    def get_prompt_variant(self) -> str:
        """Return prompt variant for teaching candidate discovery."""
        return "teaching_discovery"

    def _get_gatable_dimensions(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Determine which dimensions to probe for TEACHING DISCOVERY phase.

        Phase 2 priorities (goal already identified):
        - High: uncertainty_tolerance, pacing_preference (critical for ZPD and teaching)
        - Medium: entry_mode (for framing)
        - Low: curiosity_type, motivation, interest_phase (already know direction)

        Returns dict with:
          - gatable: list of dimension names that need more signal
          - exhausted: list of dimension names that are confident enough
          - urgency_multipliers: dict of dimension -> float urgency boost
        """
        confidence_threshold = 0.7
        gatable = []
        exhausted = []
        urgency_multipliers = {}
        profile = schema.user_profile

        print("[TEACHING_DISCOVERY] Phase 2 dimension gating")

        # Uncertainty tolerance - HIGH priority (critical for ZPD calibration)
        if profile.uncertainty_tolerance.confidence < confidence_threshold:
            gatable.append("uncertainty_tolerance")
            # Boost even more on deflection
            if schema.controller and schema.controller.branch_condition == "deflection":
                urgency_multipliers["uncertainty_tolerance"] = 0.95
            else:
                urgency_multipliers["uncertainty_tolerance"] = 0.9
        else:
            exhausted.append("uncertainty_tolerance")

        # Pacing preference - HIGH priority (affects teaching approach)
        if profile.pacing_preference.confidence < confidence_threshold:
            gatable.append("pacing_preference")
            urgency_multipliers["pacing_preference"] = 0.8
        else:
            exhausted.append("pacing_preference")

        # Entry mode - MEDIUM priority (useful for framing the teaching)
        entry = profile.entry_mode
        if max(entry.people, entry.problems, entry.ideas) < confidence_threshold:
            gatable.append("entry_mode")
            urgency_multipliers["entry_mode"] = 0.4
        else:
            exhausted.append("entry_mode")

        # Curiosity type - LOW priority (goal already provides direction)
        if profile.curiosity_type.confidence < confidence_threshold:
            gatable.append("curiosity_type")
            urgency_multipliers["curiosity_type"] = 0.2
        else:
            exhausted.append("curiosity_type")

        # Interest phase - LOW priority (mainly for teaching calibration)
        if profile.interest_phase_default.confidence < confidence_threshold:
            gatable.append("interest_phase")
            urgency_multipliers["interest_phase"] = 0.2
        else:
            exhausted.append("interest_phase")

        # Motivation profile - LOW priority (already understood from Phase 1)
        mot = profile.motivation_profile
        if max(mot.intrinsic_value, mot.utility_value, mot.identity_value) < 0.5:
            gatable.append("motivation_profile")
            urgency_multipliers["motivation_profile"] = 0.2
        else:
            exhausted.append("motivation_profile")

        return {
            "gatable": gatable,
            "exhausted": exhausted,
            "urgency_multipliers": urgency_multipliers
        }

    def _should_skip_themes_update(self, schema: DiscoverySchema) -> bool:
        """
        More aggressive theme skipping for Phase 2.

        In teaching discovery, we care more about teaching candidates than themes.
        Skip when:
        - We have a teaching candidate with decent readiness (>0.6)
        - We're past turn 4

        Returns:
            True if themes update can be skipped
        """
        if schema.interview_state.turns_elapsed < 4:
            return False

        # Lower threshold for Phase 2 - we have a goal, just need a teaching point
        for candidate in schema.teaching_candidates:
            if candidate.readiness_score >= 0.6:
                print("[TEACHING_DISCOVERY] Skipping themes - have promising candidate")
                return True

        return False

    def _is_teaching_ready(self, candidate: TeachingCandidate) -> Tuple[bool, str]:
        """
        Check if a teaching candidate is ready based on readiness_score.
        
        Simple threshold: propose when score >= 0.7
        
        Returns:
            Tuple of (ready: bool, reason: str)
        """
        READINESS_THRESHOLD = 0.7
        
        if candidate.readiness_score >= READINESS_THRESHOLD:
            return True, f"Score {candidate.readiness_score:.2f} >= {READINESS_THRESHOLD}"
        
        return False, f"Score {candidate.readiness_score:.2f} < {READINESS_THRESHOLD}"

    def _check_teaching_readiness(
        self, 
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Check if any teaching candidate is worth mentioning briefly.
        
        Returns brief suggestion message instead of transition.
        This allows conversation to continue naturally without blocking.

        Returns:
            TeachingRecommendation dictionary with suggestion message if candidate found
        """
        try:
            # Fast-path: no teaching candidates
            if not schema.teaching_candidates:
                return self._not_ready_recommendation()

            # Find the best candidate by readiness_score (still useful as a ranking metric)
            best = max(schema.teaching_candidates, key=lambda c: c.readiness_score)

            # Check if candidate is interesting enough to mention (lower threshold for brief mentions)
            # We mention candidates earlier than we would transition to teaching
            MIN_MENTION_SCORE = 0.5  # Lower threshold for brief mentions
            if best.readiness_score < MIN_MENTION_SCORE:
                return self._not_ready_recommendation()

            # Check source theme for hopeless confusion
            if best.source_theme_id is not None:
                for theme in schema.conversational_themes:
                    if theme.id == best.source_theme_id and theme.confusion_type == "hopeless":
                        print(f"[TEACHING_DISCOVERY] Skipping mention - source theme has hopeless confusion")
                        return self._not_ready_recommendation()

            # Check if we've already mentioned this candidate (avoid repeating)
            mentioned_candidates = getattr(schema.interview_state, 'teaching_candidates_mentioned', [])
            if best.id in mentioned_candidates:
                return self._not_ready_recommendation()

            user_goal = schema.interview_state.user_goal if schema.interview_state else None

            print(f"[TEACHING_DISCOVERY] Found interesting candidate '{best.topic}' (score: {best.readiness_score:.2f}) - generating brief mention")
            
            # Generate brief suggestion message (non-blocking, conversational)
            suggestion = f"I noticed {best.topic} might be worth exploring deeper - you can see it in the sidebar if you want to dive in."

            return {
                "ready": False,  # Not ready for transition, just worth mentioning
                "target_topic_id": best.id,
                "target_topic": best.topic,
                "suggestion_message": suggestion,  # Brief mention instead of transition
                "angle": getattr(best, "angle", None),
            }

        except Exception as e:
            print(f"[ERROR] Error checking teaching readiness: {e}")
            import traceback
            traceback.print_exc()
            return self._not_ready_recommendation()

    def _generate_transition_message(
        self,
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]],
        teaching_candidate: TeachingCandidate,
        user_goal: str
    ) -> str:
        """
        Generate a sophisticated, personalized transition message using LLM.
        
        This creates a natural bridge from the goal chat to the specific teaching
        candidate, using all collected context about the user.
        """
        try:
            # Gather context
            prior_knowledge = schema.prior_knowledge_assessment
            concepts_known = []
            if prior_knowledge:
                # Use granular concept_knowledge if available (has proficiency info)
                if prior_knowledge.concept_knowledge:
                    for ck in prior_knowledge.concept_knowledge[:5]:
                        concepts_known.append(f"- {ck.concept} ({ck.proficiency})")
                # Fall back to simple concepts_known strings
                elif prior_knowledge.concepts_known:
                    for concept in prior_knowledge.concepts_known[:5]:
                        concepts_known.append(f"- {concept}")
            
            learning_style = []
            if schema.user_profile:
                if schema.user_profile.pacing_preference.value:
                    learning_style.append(f"Pacing: {schema.user_profile.pacing_preference.value}")
                if schema.user_profile.curiosity_type.value:
                    learning_style.append(f"Curiosity: {schema.user_profile.curiosity_type.value}")
            
            # Get recent conversation for context
            recent_exchange = ""
            if conversation_history and len(conversation_history) >= 2:
                last_user = next((m["content"] for m in reversed(conversation_history) if m["role"] == "user"), "")
                recent_exchange = f"User's last message: {last_user[:300]}" if last_user else ""
            
            prompt = f"""You are a learning guide transitioning from exploration to focused teaching.

CONTEXT:
- User's goal: {user_goal or "General learning"}
- Teaching topic: {teaching_candidate.topic}
- User's knowledge level: {prior_knowledge.assessed_level if prior_knowledge else "intermediate"}
- Why this topic matters: {teaching_candidate.stakes_summary or teaching_candidate.identified_gap or "Key building block for their goal"}
{f"- Concepts they know: {chr(10).join(concepts_known)}" if concepts_known else ""}
{f"- Learning preferences: {', '.join(learning_style)}" if learning_style else ""}
{recent_exchange}

TASK: Write a short, natural transition (2-3 sentences) that:
1. Acknowledges what they shared and connects it to the teaching topic
2. Frames WHY this specific topic is a good starting point for THEM
3. Ends with an engaging question that invites them to explore deeper

STYLE:
- Conversational and warm, not formal
- Specific to their interests, not generic
- Shows you understood their background
- NO templated phrases like "Great starting point" or "Let's explore"
- NO flattery or over-enthusiasm

Write the transition:"""

            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_override or "openai:gpt-4o"
            )
            
            print(f"[TRANSITION] Generated personalized transition message")
            return response.strip()
            
        except Exception as e:
            print(f"[ERROR] Failed to generate transition message: {e}")
            # Fallback to a simple but natural message
            return f"Based on what you've shared, {teaching_candidate.topic} seems like a natural place to start. What aspects of this are you most curious about?"

    def _update_prior_knowledge_assessment(
        self,
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> Dict[str, Any]:
        """
        Analyze user's response to update prior knowledge assessment.
        
        This helps calibrate teaching to the user's actual level.
        
        Returns:
            Updated assessment dictionary
        """
        try:
            # Get the last AI message (the question we asked)
            ai_question = ""
            for msg in reversed(conversation_history[:-1]):  # Exclude the current user message
                if msg.get("role") == "assistant":
                    ai_question = msg.get("content", "")
                    break
            
            # Get current assessment state
            current_assessment = schema.prior_knowledge_assessment
            
            # Determine which technique was likely used based on controller
            technique_used = "topic_probe"  # Default
            if schema.controller:
                mode = schema.controller.conversation_mode
                if mode == "explain_back":
                    technique_used = "explain_back"
                elif mode == "scenario_probe":
                    technique_used = "scenario_probe"
                elif mode == "calibration":
                    technique_used = "calibration"
                elif mode == "topic_probe":
                    technique_used = "topic_probe"
            
            # Load the analysis prompt
            prompt_template = self.prompt_loader.load_ranker_prompt(
                "analyze_assessment", 
                variant=self.get_prompt_variant()
            )
            
            user_goal = schema.interview_state.user_goal or "Not yet identified"
            
            # Format concept knowledge with proficiency levels
            concept_knowledge_str = "none yet"
            if current_assessment.concept_knowledge:
                concept_knowledge_str = "\n".join([
                    f"  - {ck.concept} [{ck.proficiency}]" + (f" (evidence: {ck.evidence[:100]}...)" if ck.evidence and len(ck.evidence) > 100 else f" (evidence: {ck.evidence})" if ck.evidence else "")
                    for ck in current_assessment.concept_knowledge
                ])
            
            formatted_prompt = prompt_template.format(
                user_goal=user_goal,
                technique_used=technique_used,
                ai_question=ai_question[:500],  # Truncate for context
                user_response=user_message[:1000],  # Truncate
                current_level=current_assessment.assessed_level or "unknown",
                concept_knowledge=concept_knowledge_str,
                techniques_used=", ".join(current_assessment.techniques_used) or "none yet",
                current_confidence=current_assessment.confidence
            )
            
            messages = [{"role": "user", "content": formatted_prompt}]
            
            # Use ranker model
            from src.config import get_model_name
            model = self.model_override if self.model_override else get_model_name(
                "ranker", "assessment", default="gpt-4o"
            )
            
            response = self.llm.chat_with_json(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=800,
                json_top_level="object"
            )
            
            print(f"[ASSESSMENT] Level: {response.get('assessed_level')}, Confidence: {response.get('level_confidence', 0):.2f}")
            print(f"[ASSESSMENT] Ready for task proposal: {response.get('ready_for_task_proposal', False)}")
            
            return response
            
        except Exception as e:
            print(f"[ERROR] Error updating prior knowledge assessment: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def update_schema(
        self,
        current_schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> DiscoverySchema:
        """
        Phase 2 schema update: Focus on finding teaching candidate.

        Execution order (phased for correct dependencies):
        - PHASE 1: branch_condition, user_profile, conversational_themes (parallel)
        - PHASE 1.5: prior knowledge assessment (uses user's response)
        - PHASE 2: teaching_candidates (sequential - needs fresh themes + assessment)
        - PHASE 3: controller + readiness (parallel)

        Updates:
        - prior_knowledge_assessment (NEW!)
        - teaching_candidates (primary focus)
        - user_profile
        - conversational_themes
        - controller
        - teaching_recommendation

        Does NOT update:
        - goal_candidates (Phase 1 concern, goal already identified)

        Returns updated schema with teaching_recommendation if ready.
        """
        total_start = time.time()
        print(f"\n[TEACHING_DISCOVERY] ===== PHASE 2: FINDING TEACHING TARGET =====")

        user_goal = current_schema.interview_state.user_goal
        if user_goal:
            print(f"[TEACHING_DISCOVERY] Goal: '{user_goal}'")

        # Determine which calls to skip
        skip_profile = self._should_skip_profile_update(current_schema)
        skip_themes = self._should_skip_themes_update(current_schema)

        if skip_profile:
            print("[TIMING] Skipping profile update (high confidence)")
        if skip_themes:
            print("[TIMING] Skipping themes update (stable themes)")

        # ===== PHASE 1: Foundation (parallel - no dependencies) =====
        print("[TIMING] Phase 1: branch + profile + themes (parallel)...")
        phase1_start = time.time()

        # Use scheduler to control concurrency
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Always run branch classification
            branch_run_id = f"branch_{uuid.uuid4().hex[:8]}"
            acquired_branch, reason = self.scheduler.acquire(branch_run_id)
            if not acquired_branch:
                print(f"[Scheduler] Could not acquire slot for branch classification: {reason}, executing anyway")
            future_branch = executor.submit(
                self._classify_branch_condition,
                user_message,
                conversation_history
            )

            # Conditionally run profile and themes
            future_profile = None
            future_themes = None
            acquired_profile = False
            acquired_themes = False
            profile_run_id = None
            themes_run_id = None

            if not skip_profile:
                profile_run_id = f"profile_{uuid.uuid4().hex[:8]}"
                acquired_profile, reason = self.scheduler.acquire(profile_run_id)
                if not acquired_profile:
                    print(f"[Scheduler] Could not acquire slot for profile update: {reason}, executing anyway")
                future_profile = executor.submit(
                    self._update_user_profile,
                    current_schema,
                    conversation_history
                )

            if not skip_themes:
                themes_run_id = f"themes_{uuid.uuid4().hex[:8]}"
                acquired_themes, reason = self.scheduler.acquire(themes_run_id)
                if not acquired_themes:
                    print(f"[Scheduler] Could not acquire slot for themes update: {reason}, executing anyway")
                future_themes = executor.submit(
                    self._update_conversational_themes,
                    current_schema,
                    conversation_history,
                    current_schema.interview_state.turns_elapsed + 1
                )

            # Wait for Phase 1 to complete
            try:
                branch_condition = future_branch.result()
            finally:
                if acquired_branch:
                    self.scheduler.release(branch_run_id)
            
            if future_profile:
                try:
                    profile_updates = future_profile.result()
                finally:
                    if acquired_profile and profile_run_id:
                        self.scheduler.release(profile_run_id)
            else:
                profile_updates = None
            
            if future_themes:
                try:
                    theme_updates = future_themes.result()
                finally:
                    if acquired_themes and themes_run_id:
                        self.scheduler.release(themes_run_id)
            else:
                theme_updates = None

        print(f"[TIMING] Phase 1 completed: {time.time() - phase1_start:.2f}s")

        # Assemble temp_schema with Phase 1 results (fresh themes + profile)
        temp_schema = current_schema.model_copy(deep=True)
        
        if profile_updates:
            # Preserve communication_style if not in updates (LLM might not return it)
            if "communication_style" not in profile_updates:
                profile_updates["communication_style"] = current_schema.user_profile.communication_style.model_dump()
            # Ensure communication_style has all required fields
            elif profile_updates.get("communication_style") is None:
                profile_updates["communication_style"] = current_schema.user_profile.communication_style.model_dump()
            else:
                # Merge with existing to ensure all fields are present
                existing_comm = current_schema.user_profile.communication_style.model_dump()
                new_comm = profile_updates.get("communication_style", {})
                # Handle case where new_comm might be None or not a dict
                if not isinstance(new_comm, dict):
                    new_comm = {}
                # Merge, but use existing values for any None values in new_comm, with fallback to defaults
                merged_comm = {
                    "verbosity": (new_comm.get("verbosity") if new_comm.get("verbosity") is not None else existing_comm.get("verbosity")) or "medium",
                    "complexity": (new_comm.get("complexity") if new_comm.get("complexity") is not None else existing_comm.get("complexity")) or "medium",
                    "emotional_expression": (new_comm.get("emotional_expression") if new_comm.get("emotional_expression") is not None else existing_comm.get("emotional_expression")) or "neutral",
                    "question_asking_frequency": (new_comm.get("question_asking_frequency") if new_comm.get("question_asking_frequency") is not None else existing_comm.get("question_asking_frequency")) or "medium"
                }
                profile_updates["communication_style"] = merged_comm
            
            temp_schema.user_profile = UserProfile(**profile_updates)
        
        if theme_updates:
            temp_schema.conversational_themes = [ConversationalTheme(**t) for t in theme_updates]

        # ===== PHASE 1.5: Prior Knowledge Assessment =====
        print("[TIMING] Phase 1.5: prior knowledge assessment...")
        phase1_5_start = time.time()
        
        assessment_updates = self._update_prior_knowledge_assessment(
            temp_schema,
            conversation_history,
            user_message
        )
        
        if assessment_updates:
            # Update the assessment in schema
            current_assessment = temp_schema.prior_knowledge_assessment
            
            # Update level if provided and confidence is higher
            if assessment_updates.get("assessed_level"):
                new_confidence = assessment_updates.get("level_confidence", 0)
                if new_confidence > current_assessment.confidence:
                    current_assessment.assessed_level = assessment_updates["assessed_level"]
                    current_assessment.confidence = new_confidence
            
            # NEW: Handle granular concept_updates with proficiency levels
            from src.schema.full_schema import ConceptKnowledge
            for concept_update in assessment_updates.get("concept_updates", []):
                concept_name = concept_update.get("concept", "")
                proficiency = concept_update.get("proficiency", "heard_of")
                evidence = concept_update.get("evidence")
                is_gap = concept_update.get("is_gap", False)
                
                if concept_name:
                    # Check if concept already exists
                    existing = next((c for c in current_assessment.concept_knowledge if c.concept == concept_name), None)
                    
                    if existing:
                        # Update proficiency if new assessment is more confident
                        proficiency_order = ["heard_of", "understands_basics", "can_explain", "can_apply", "expert"]
                        if proficiency_order.index(proficiency) > proficiency_order.index(existing.proficiency):
                            existing.proficiency = proficiency
                            existing.evidence = evidence
                    else:
                        # Add new concept
                        current_assessment.concept_knowledge.append(
                            ConceptKnowledge(concept=concept_name, proficiency=proficiency, evidence=evidence)
                        )
                    
                    # Also update legacy lists for backwards compatibility
                    if is_gap:
                        if concept_name not in current_assessment.concepts_unclear:
                            current_assessment.concepts_unclear.append(concept_name)
                    else:
                        if concept_name not in current_assessment.concepts_known:
                            current_assessment.concepts_known.append(concept_name)
            
            # LEGACY: Also handle old format for backwards compatibility
            for concept in assessment_updates.get("new_concepts_known", []):
                if concept and concept not in current_assessment.concepts_known:
                    current_assessment.concepts_known.append(concept)
            
            for concept in assessment_updates.get("new_concepts_unclear", []):
                if concept and concept not in current_assessment.concepts_unclear:
                    current_assessment.concepts_unclear.append(concept)
            
            # Update practical experience if provided
            if assessment_updates.get("practical_experience"):
                current_assessment.practical_experience = assessment_updates["practical_experience"]
            
            # Accumulate learning style hints
            for hint in assessment_updates.get("learning_style_hints", []):
                if hint and hint not in current_assessment.learning_style_hints:
                    current_assessment.learning_style_hints.append(hint)
            
            # Add evidence
            if assessment_updates.get("evidence"):
                ev = assessment_updates["evidence"]
                # Handle case where LLM returns revealed as a list instead of string
                revealed = ev.get("revealed", "")
                if isinstance(revealed, list):
                    revealed = "; ".join(str(r) for r in revealed)
                quote = ev.get("quote", "")
                if isinstance(quote, list):
                    quote = "; ".join(str(q) for q in quote)
                    
                current_assessment.evidence.append(
                    AssessmentEvidence(
                        technique=str(ev.get("technique", "unknown")),
                        quote=str(quote),
                        revealed=str(revealed)
                    )
                )
                # Track technique used
                technique = str(ev.get("technique", "unknown"))
                if technique not in current_assessment.techniques_used:
                    current_assessment.techniques_used.append(technique)
            
            temp_schema.prior_knowledge_assessment = current_assessment
        
        print(f"[TIMING] Phase 1.5 completed: {time.time() - phase1_5_start:.2f}s")

        # ===== PHASE 2+3: Teaching candidates + Controller + Readiness (PARALLEL) =====
        # Controller uses profile/themes/branch but not teaching candidates,
        # so we can run all three concurrently for ~2x speedup.
        print(f"[TIMING] Phase 2+3: teaching candidates + controller + readiness (PARALLEL)")
        phase2_start = time.time()

        # Preserve goal_candidates (not updated in Phase 2)
        temp_schema.goal_candidates = current_schema.goal_candidates

        def _run_teaching_candidates():
            return self._update_teaching_candidates(
                temp_schema,
                conversation_history,
                current_schema.interview_state.turns_elapsed + 1
            )

        def _run_teaching_readiness():
            return self._check_teaching_readiness(temp_schema, conversation_history)

        teaching_updates = None
        controller_dict = None
        teaching_rec_dict = None

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_teaching = executor.submit(_run_teaching_candidates)
            future_controller = executor.submit(self._generate_controller, temp_schema, branch_condition, user_message)
            future_readiness = executor.submit(_run_teaching_readiness)

            for future in as_completed([future_teaching, future_controller, future_readiness]):
                try:
                    if future is future_teaching:
                        teaching_updates = future.result()
                        print(f"[TIMING] teaching_candidates completed in {time.time() - phase2_start:.2f}s")
                    elif future is future_controller:
                        controller_dict = future.result()
                        print(f"[TIMING] controller completed in {time.time() - phase2_start:.2f}s")
                    else:
                        teaching_rec_dict = future.result()
                        print(f"[TIMING] teaching_readiness completed in {time.time() - phase2_start:.2f}s")
                except Exception as e:
                    print(f"[TIMING] Parallel task error: {e}")
                    import traceback
                    traceback.print_exc()

        # Apply teaching candidate updates
        if teaching_updates:
            temp_schema.teaching_candidates = [TeachingCandidate(**t) for t in teaching_updates]

        # Ensure controller_dict exists
        if not controller_dict:
            controller_dict = self._generate_controller(temp_schema, branch_condition, user_message)
        if not controller_dict.get("branch_condition") or controller_dict.get("branch_condition") is None:
            controller_dict["branch_condition"] = branch_condition or "unclear"

        # Ensure teaching_rec_dict exists
        if not teaching_rec_dict:
            teaching_rec_dict = self._check_teaching_readiness(temp_schema, conversation_history)

        print(f"[TIMING] Phase 2+3 completed: {time.time() - phase2_start:.2f}s")

        # Build final schema
        final_schema = temp_schema.model_copy(deep=True)

        # Curriculum generation is manual-only via "Generate Learning Path" button.
        # Teaching candidate discovery continues in the background.
        # Safety check: ensure propose_tasks is never set automatically
        if controller_dict.get("conversation_mode") == "propose_tasks":
            print(f"[RANKER] DEBUG: Controller LLM returned propose_tasks mode")
            print(f"[RANKER] DEBUG: task_curriculum.proposed = {final_schema.task_curriculum.proposed}")
            if not final_schema.task_curriculum.proposed:
                print(f"[RANKER] WARNING: LLM tried to set propose_tasks mode - overriding to general_continuation")
                print(f"[RANKER] Curriculum generation is manual-only via button")
                controller_dict["conversation_mode"] = "general_continuation"
                controller_dict["next_action"] = "continue_exploration"
                controller_dict["question_intent"] = "general_continuation"
            else:
                print(f"[RANKER] INFO: propose_tasks mode is valid (curriculum already proposed via button)")

        # INFRASTRUCTURE FIX: Handle invalid conversation_mode gracefully
        try:
            final_schema.controller = Controller(**controller_dict)
        except Exception as e:
            print(f"[CONTROLLER ERROR] Failed to create Controller: {e}")

            # If conversation_mode is invalid, try fallback to direct_probe
            if "conversation_mode" in str(e):
                invalid_mode = controller_dict.get("conversation_mode")
                print(f"[CONTROLLER ERROR] Invalid conversation_mode: '{invalid_mode}'")
                print(f"[CONTROLLER ERROR] Falling back to 'direct_probe'")

                # Create fallback controller with safe mode
                controller_dict["conversation_mode"] = "direct_probe"
                final_schema.controller = Controller(**controller_dict)
            else:
                # Other validation error - re-raise
                raise

        # Handle teaching candidate suggestions (brief mentions)
        if teaching_rec_dict.get("suggestion_message"):
            # Mark candidate as mentioned to avoid repeating
            candidate_id = teaching_rec_dict.get("target_topic_id")
            if candidate_id and candidate_id not in final_schema.interview_state.teaching_candidates_mentioned:
                final_schema.interview_state.teaching_candidates_mentioned.append(candidate_id)
        
        final_schema.teaching_recommendation = TeachingRecommendation(**teaching_rec_dict)

        # Update interview state
        final_schema.interview_state.turns_elapsed += 1

        # Track question intent to avoid repetition
        if controller_dict.get("question_intent"):
            intents = list(final_schema.interview_state.recent_question_intents)
            intents.append(controller_dict["question_intent"])
            final_schema.interview_state.recent_question_intents = intents[-5:]

        # Track focus instruction summaries
        if controller_dict.get("focus_instruction"):
            summaries = list(final_schema.interview_state.recent_question_summaries)
            summaries.append(controller_dict["focus_instruction"][:100])
            final_schema.interview_state.recent_question_summaries = summaries[-5:]

        # Debug output
        if final_schema.teaching_candidates:
            best = max(final_schema.teaching_candidates, key=lambda c: c.readiness_score)
            print(f"[TEACHING_DISCOVERY] Best candidate: '{best.topic}' ({best.readiness_score:.2f})")

        print(f"[TIMING] Total schema update: {time.time() - total_start:.2f}s\n")
        return final_schema

