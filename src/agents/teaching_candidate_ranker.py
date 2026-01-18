"""Teaching candidate ranker for Phase 2: finding a teachable topic."""
from typing import Dict, Any, List, Tuple
import time
from concurrent.futures import ThreadPoolExecutor
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

    def _check_teaching_readiness(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Check if any teaching candidate is ready.

        Uses explicit criteria rather than LLM-determined readiness.

        Returns:
            TeachingRecommendation dictionary
        """
        try:
            # Fast-path: no teaching candidates
            if not schema.teaching_candidates:
                return self._not_ready_recommendation()

            # Find the best candidate by readiness_score (still useful as a ranking metric)
            best = max(schema.teaching_candidates, key=lambda c: c.readiness_score)

            # Check readiness based on score threshold
            ready, reason = self._is_teaching_ready(best)
            print(f"[TEACHING_DISCOVERY] Candidate '{best.topic}': ready={ready}, reason={reason}")

            if not ready:
                return self._not_ready_recommendation()

            # Check source theme for hopeless confusion
            if best.source_theme_id is not None:
                for theme in schema.conversational_themes:
                    if theme.id == best.source_theme_id and theme.confusion_type == "hopeless":
                        print(f"[TEACHING_DISCOVERY] Rejected - source theme has hopeless confusion")
                        return self._not_ready_recommendation()

            # Build recommendation
            pacing = schema.user_profile.pacing_preference.value or "exploratory"
            focus_q = getattr(best, "focus_question", None) or None
            user_goal = schema.interview_state.user_goal if schema.interview_state else None

            print(f"[TEACHING_DISCOVERY] Ready! Teaching '{best.topic}'")

            return {
                "ready": True,
                "target_topic_id": best.id,
                "target_topic": best.topic,
                "focus_question": focus_q,
                "angle": getattr(best, "angle", None),
                "difficulty_calibration": (
                    f"Entry point toward goal: {user_goal}" 
                    if user_goal 
                    else "Best first step toward your learning goal"
                ),
                "format": "short explanation + check understanding",
                "pacing": pacing,
                "first_move": (
                    f"This is a great starting point toward {user_goal}. {focus_q}"
                    if (user_goal and focus_q)
                    else f"This is the right first step. {focus_q if focus_q else 'Ready to dive in?'}"
                )
            }

        except Exception as e:
            print(f"[ERROR] Error checking teaching readiness: {e}")
            import traceback
            traceback.print_exc()
            return self._not_ready_recommendation()

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

        with ThreadPoolExecutor(max_workers=3) as executor:
            # Always run branch classification
            future_branch = executor.submit(
                self._classify_branch_condition,
                user_message,
                conversation_history
            )

            # Conditionally run profile and themes
            future_profile = None
            future_themes = None

            if not skip_profile:
                future_profile = executor.submit(
                    self._update_user_profile,
                    current_schema,
                    conversation_history
                )

            if not skip_themes:
                future_themes = executor.submit(
                    self._update_conversational_themes,
                    current_schema,
                    conversation_history,
                    current_schema.interview_state.turns_elapsed + 1
                )

            # Wait for Phase 1 to complete
            branch_condition = future_branch.result()
            profile_updates = future_profile.result() if future_profile else None
            theme_updates = future_themes.result() if future_themes else None

        print(f"[TIMING] Phase 1 completed: {time.time() - phase1_start:.2f}s")

        # Assemble temp_schema with Phase 1 results (fresh themes + profile)
        temp_schema = current_schema.model_copy(deep=True)
        
        if profile_updates:
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

        # ===== PHASE 2: Teaching candidates (GATED on assessment confidence) =====
        # Only discover teaching candidates when we've assessed the user's level
        assessment_confidence = temp_schema.prior_knowledge_assessment.confidence
        ASSESSMENT_THRESHOLD = 0.6  # Need at least 60% confidence before proposing tasks
        
        if assessment_confidence >= ASSESSMENT_THRESHOLD:
            print(f"[TIMING] Phase 2: teaching candidates (assessment confidence {assessment_confidence:.2f} >= {ASSESSMENT_THRESHOLD})")
            phase2_start = time.time()

            teaching_updates = self._update_teaching_candidates(
                temp_schema,  # Now has fresh themes!
                conversation_history,
                current_schema.interview_state.turns_elapsed + 1
            )

            # Apply teaching candidate updates
            if teaching_updates:
                temp_schema.teaching_candidates = [TeachingCandidate(**t) for t in teaching_updates]
            
            print(f"[TIMING] Phase 2 completed: {time.time() - phase2_start:.2f}s")
        else:
            print(f"[ASSESSMENT] Skipping Phase 2 - assessment confidence {assessment_confidence:.2f} < {ASSESSMENT_THRESHOLD}")
            print(f"[ASSESSMENT] Still gathering prior knowledge. Techniques used: {temp_schema.prior_knowledge_assessment.techniques_used}")
            # Keep existing teaching candidates (don't wipe them)
            temp_schema.teaching_candidates = current_schema.teaching_candidates

        # Preserve goal_candidates (not updated in Phase 2)
        temp_schema.goal_candidates = current_schema.goal_candidates

        # ===== PHASE 3: Controller + readiness (parallel) =====
        print("[TIMING] Phase 3: controller + readiness (parallel)...")
        phase3_start = time.time()

        def _teaching_rec_task() -> Dict[str, Any]:
            # Check teaching readiness (no minimum turn requirement)
            return self._check_teaching_readiness(temp_schema)

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_controller = executor.submit(self._generate_controller, temp_schema, branch_condition)
            future_teaching_rec = executor.submit(_teaching_rec_task)

            controller_dict = future_controller.result()
            teaching_rec_dict = future_teaching_rec.result()

        print(f"[TIMING] Phase 3 completed: {time.time() - phase3_start:.2f}s")

        # Build final schema
        final_schema = temp_schema.model_copy(deep=True)
        final_schema.controller = Controller(**controller_dict)
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

