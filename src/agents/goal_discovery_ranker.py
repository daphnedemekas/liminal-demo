"""Goal discovery ranker for Phase 1: finding a learning goal."""
from typing import Dict, Any, List, Tuple
import time
from concurrent.futures import ThreadPoolExecutor
from src.agents.ranker_base import RankerAgentBase
from src.schema.full_schema import (
    DiscoverySchema,
    UserProfile,
    ConversationalTheme,
    GoalCandidate,
    Controller,
    TeachingRecommendation
)


class GoalDiscoveryRanker(RankerAgentBase):
    """
    Ranker for Phase 1: Discovering the user's learning goal.

    Used when user has no stated goal. This ranker:
    - Updates goal_candidates (NOT teaching_candidates)
    - Tracks goal readiness scores
    - Signals when a goal is ready (readiness >= 0.7)
    - Focuses on curiosity patterns and interest signals

    Dimension priorities (Phase 1):
    - High: curiosity_type (0.8), entry_mode (0.7), motivation_profile (0.6)
    - Medium: interest_phase (0.3)
    - Low: pacing_preference (0.2), uncertainty_tolerance (0.2)
    """

    def get_prompt_variant(self) -> str:
        """Return prompt variant for goal discovery phase."""
        return "goal_discovery"

    def _get_gatable_dimensions(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Determine which dimensions to probe for GOAL DISCOVERY phase.

        Phase 1 priorities:
        - High: curiosity_type, entry_mode, motivation_profile
        - Medium: interest_phase
        - Low: pacing, uncertainty_tolerance (not critical for finding goal)

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

        print("[GOAL_DISCOVERY] Phase 1 dimension gating")

        # Curiosity type - HIGH priority (key to finding goal direction)
        if profile.curiosity_type.confidence < confidence_threshold:
            gatable.append("curiosity_type")
            urgency_multipliers["curiosity_type"] = 0.8
        else:
            exhausted.append("curiosity_type")

        # Entry mode - HIGH priority (people/problems/ideas frame goal exploration)
        entry = profile.entry_mode
        if max(entry.people, entry.problems, entry.ideas) < confidence_threshold:
            gatable.append("entry_mode")
            urgency_multipliers["entry_mode"] = 0.7
        else:
            exhausted.append("entry_mode")

        # Motivation profile - HIGH priority (helps understand what drives them)
        mot = profile.motivation_profile
        if max(mot.intrinsic_value, mot.utility_value, mot.identity_value) < 0.5:
            gatable.append("motivation_profile")
            urgency_multipliers["motivation_profile"] = 0.6
        else:
            exhausted.append("motivation_profile")

        # Interest phase - MEDIUM priority (useful context)
        if profile.interest_phase_default.confidence < confidence_threshold:
            gatable.append("interest_phase")
            urgency_multipliers["interest_phase"] = 0.3
        else:
            exhausted.append("interest_phase")

        # Pacing preference - LOW priority (not critical for goal discovery)
        if profile.pacing_preference.confidence < confidence_threshold:
            gatable.append("pacing_preference")
            urgency_multipliers["pacing_preference"] = 0.2
        else:
            exhausted.append("pacing_preference")

        # Uncertainty tolerance - LOW priority (more relevant for teaching)
        if profile.uncertainty_tolerance.confidence < confidence_threshold:
            gatable.append("uncertainty_tolerance")
            urgency_multipliers["uncertainty_tolerance"] = 0.2
        else:
            exhausted.append("uncertainty_tolerance")

        return {
            "gatable": gatable,
            "exhausted": exhausted,
            "urgency_multipliers": urgency_multipliers
        }

    def _is_goal_ready(self, goal: GoalCandidate) -> Tuple[bool, str]:
        """
        Check if a goal is ready based on explicit dimension criteria.
        
        Criteria:
        - All dimensions >= MIN_DIMENSION (no weak dimensions)
        - Average of all dimensions >= AVG_THRESHOLD
        
        Returns:
            Tuple of (ready: bool, reason: str)
        """
        MIN_DIMENSION = 0.5
        AVG_THRESHOLD = 0.7
        
        dimensions = {
            "concreteness": goal.concreteness,
            "break_apartability": goal.break_apartability,
            "scope_appropriateness": goal.scope_appropriateness,
            "user_commitment": goal.user_commitment
        }
        
        # Check for weak dimensions
        weak = [k for k, v in dimensions.items() if v < MIN_DIMENSION]
        if weak:
            return False, f"Weak dimensions: {weak}"
        
        avg = sum(dimensions.values()) / len(dimensions)
        if avg < AVG_THRESHOLD:
            return False, f"Average {avg:.2f} below {AVG_THRESHOLD}"
        
        return True, "All criteria met"

    def _check_goal_readiness(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Check if any goal candidate is ready for confirmation.

        Uses explicit dimension criteria rather than LLM-determined readiness.
        Skips previously rejected AND accepted goals.

        Returns:
            Dict with 'ready' boolean and 'best_goal' if ready
        """
        if not schema.goal_candidates:
            return {"ready": False, "best_goal": None}

        # Find the best goal by average of dimensions
        def goal_score(g: GoalCandidate) -> float:
            return (g.concreteness + g.break_apartability + 
                    g.scope_appropriateness + g.user_commitment) / 4
        
        # Sort all goals by score, highest first
        sorted_goals = sorted(schema.goal_candidates, key=goal_score, reverse=True)
        rejected_ids = set(schema.interview_state.rejected_goal_ids)
        accepted_ids = set(schema.interview_state.accepted_goal_ids)
        
        # How many goals have been rejected? Lower threshold after rejections
        num_rejections = len(rejected_ids)
        
        # Try each goal in order of score
        for goal in sorted_goals:
            # Skip already-rejected goals
            if goal.id in rejected_ids:
                print(f"[GOAL_DISCOVERY] Skipping rejected goal: '{goal.goal}'")
                continue
            
            # Skip already-accepted goals (don't re-propose)
            if goal.id in accepted_ids:
                print(f"[GOAL_DISCOVERY] Skipping already-accepted goal: '{goal.goal}'")
                continue
            
            ready, reason = self._is_goal_ready(goal)
            print(f"[GOAL_DISCOVERY] Goal '{goal.goal}': ready={ready}, reason={reason}")
            print(f"[GOAL_DISCOVERY]   concreteness={goal.concreteness:.2f}, break_apartability={goal.break_apartability:.2f}")
            print(f"[GOAL_DISCOVERY]   scope_appropriateness={goal.scope_appropriateness:.2f}, user_commitment={goal.user_commitment:.2f}")
            
            if ready:
                return {"ready": True, "best_goal": goal}
            
            # After 1+ rejections, also accept goals that are "close enough"
            # This makes the system more aggressive about proposing alternatives
            if num_rejections >= 1 and goal_score(goal) >= 0.65:
                print(f"[GOAL_DISCOVERY] Goal '{goal.goal}' close enough after {num_rejections} rejection(s)")
                return {"ready": True, "best_goal": goal}
        
        # No ready goals found
        return {"ready": False, "best_goal": None}

    def _check_teaching_readiness(self, schema: DiscoverySchema) -> Dict[str, Any]:
        """
        Phase 1 doesn't check teaching readiness - always returns not ready.

        Teaching readiness is checked by TeachingCandidateRanker in Phase 2.
        """
        return self._not_ready_recommendation()

    def update_schema(
        self,
        current_schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> DiscoverySchema:
        """
        Phase 1 schema update: Focus on discovering learning goal.

        Execution order (phased for correct dependencies):
        - PHASE 1: branch_condition, user_profile, conversational_themes (parallel)
        - PHASE 2: goal_candidates (sequential - needs fresh themes)
        - PHASE 3: controller (uses all updates)

        Updates:
        - goal_candidates (primary focus)
        - user_profile
        - conversational_themes
        - controller

        Does NOT update:
        - teaching_candidates (Phase 2 concern)

        Returns updated schema, potentially with goal_identified=True if goal is ready.
        """
        total_start = time.time()
        print(f"\n[GOAL_DISCOVERY] ===== PHASE 1: DISCOVERING LEARNING GOAL =====")

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

        # ===== PHASE 2: Goal candidates (sequential - uses fresh themes) =====
        print("[TIMING] Phase 2: goal candidates (uses fresh themes)...")
        phase2_start = time.time()

        goal_updates = self._update_goal_candidates(
            temp_schema,  # Now has fresh themes!
            conversation_history,
            current_schema.interview_state.turns_elapsed + 1
        )

        # Apply goal candidate updates
        if goal_updates:
            temp_schema.goal_candidates = [GoalCandidate(**g) for g in goal_updates]

        # Preserve teaching_candidates (not updated in Phase 1)
        temp_schema.teaching_candidates = current_schema.teaching_candidates

        print(f"[TIMING] Phase 2 completed: {time.time() - phase2_start:.2f}s")

        # Check for phase transition: Is any goal ready?
        # MINIMUM TURN REQUIREMENT: Don't propose goals until at least 2 user responses
        # (Turn 1 is background onboarding, Turn 2+ is actual conversation)
        min_turns_for_goal = 2
        current_turn = current_schema.interview_state.turns_elapsed + 1  # +1 because we're about to increment
        
        # COOLDOWN AFTER ACCEPTING A GOAL: Require at least 2 turns of exploration before proposing another
        # This ensures we explore new threads instead of immediately proposing the next ready goal
        goal_acceptance_cooldown = 2
        last_accepted_turn = current_schema.interview_state.last_goal_accepted_turn
        turns_since_acceptance = (current_turn - last_accepted_turn) if last_accepted_turn is not None else float('inf')
        
        if current_turn < min_turns_for_goal:
            print(f"[GOAL_DISCOVERY] Too early to propose goal (turn {current_turn} < {min_turns_for_goal})")
            goal_readiness = {"ready": False, "best_goal": None}
        elif turns_since_acceptance < goal_acceptance_cooldown:
            print(f"[GOAL_DISCOVERY] In cooldown after goal acceptance ({turns_since_acceptance} < {goal_acceptance_cooldown} turns)")
            print(f"[GOAL_DISCOVERY] Will explore new threads before proposing another goal")
            goal_readiness = {"ready": False, "best_goal": None}
        else:
            goal_readiness = self._check_goal_readiness(temp_schema)
        
        if goal_readiness["ready"]:
            best_goal = goal_readiness["best_goal"]
            
            # Check if we already proposed this goal (waiting for user response)
            if (temp_schema.interview_state.proposed_goal == best_goal.goal and 
                temp_schema.interview_state.proposed_goal_id == best_goal.id):
                print(f"[GOAL_DISCOVERY] Goal '{best_goal.goal}' already proposed, waiting for user response...")
            else:
                # Propose the goal to the user (don't auto-confirm)
                print(f"\n[GOAL_DISCOVERY] ===== GOAL PROPOSED =====")
                print(f"[GOAL_DISCOVERY] Goal: '{best_goal.goal}'")
                print(f"[GOAL_DISCOVERY] Readiness: {best_goal.readiness_score:.2f}")
                temp_schema.interview_state.proposed_goal = best_goal.goal
                temp_schema.interview_state.proposed_goal_id = best_goal.id
        else:
            # Clear any pending proposal if goal no longer qualifies
            if temp_schema.interview_state.proposed_goal:
                print(f"[GOAL_DISCOVERY] Clearing stale goal proposal")
                temp_schema.interview_state.proposed_goal = None
                temp_schema.interview_state.proposed_goal_id = None
                
            if temp_schema.goal_candidates:
                # Show best non-rejected candidate
                rejected_ids = set(temp_schema.interview_state.rejected_goal_ids)
                accepted_ids = set(temp_schema.interview_state.accepted_goal_ids)
                available = [g for g in temp_schema.goal_candidates 
                            if g.id not in rejected_ids and g.id not in accepted_ids]
                if available:
                    best = max(available, key=lambda g: g.readiness_score)
                    print(f"[GOAL_DISCOVERY] Best available candidate: '{best.goal}' ({best.readiness_score:.2f})")
                else:
                    print(f"[GOAL_DISCOVERY] No available candidates (all rejected or accepted)")

        # ===== PHASE 3: Controller (uses all updates) =====
        print("[TIMING] Phase 3: controller generation...")
        phase3_start = time.time()
        controller_dict = self._generate_controller(temp_schema, branch_condition)
        print(f"[TIMING] Phase 3 completed: {time.time() - phase3_start:.2f}s")

        # Build final schema
        final_schema = temp_schema.model_copy(deep=True)
        final_schema.controller = Controller(**controller_dict)
        
        # Phase 1 never recommends teaching
        final_schema.teaching_recommendation = TeachingRecommendation(**self._not_ready_recommendation())

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

        print(f"[TIMING] Total schema update: {time.time() - total_start:.2f}s\n")
        return final_schema

