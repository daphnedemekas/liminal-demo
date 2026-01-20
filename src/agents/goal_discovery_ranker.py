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

    def _check_goal_relevance(
        self, 
        goal: GoalCandidate, 
        conversation_history: List[Dict[str, str]],
        schema: DiscoverySchema = None,
        recent_turns: int = 4
    ) -> float:
        """
        Check how relevant a goal is to recent conversation context.
        
        Returns a relevance score (0.0-1.0) based on:
        - How well the goal matches recent user messages
        - How well it aligns with recent conversational themes
        - Semantic keyword matching for common topics
        
        Args:
            goal: The goal candidate to check
            conversation_history: Full conversation history
            schema: Current schema (for accessing themes)
            recent_turns: Number of recent turns to consider (default 4)
        
        Returns:
            Relevance score between 0.0 and 1.0
        """
        if not conversation_history:
            return 0.5  # Neutral if no history
        
        # Get recent user messages (last N turns, focus on user messages)
        recent_messages = conversation_history[-recent_turns * 2:] if len(conversation_history) > recent_turns * 2 else conversation_history
        recent_user_text = " ".join([
            msg.get("content", "") for msg in recent_messages 
            if msg.get("role") == "user"
        ]).lower()
        
        if not recent_user_text:
            return 0.5  # Neutral if no recent user messages
        
        # Extract key terms from the goal
        goal_text = goal.goal.lower()
        goal_terms = set(goal_text.split())
        
        # Extract key terms from recent conversation
        # Remove common stop words
        stop_words = {"i", "am", "is", "are", "was", "were", "be", "been", "being", 
                     "have", "has", "had", "do", "does", "did", "will", "would", 
                     "should", "could", "may", "might", "can", "to", "the", "a", 
                     "an", "and", "or", "but", "in", "on", "at", "for", "of", "with",
                     "about", "from", "as", "it", "this", "that", "these", "those",
                     "what", "which", "who", "where", "when", "why", "how", "want",
                     "would", "like", "love", "enjoy", "feel", "think", "know"}
        
        user_terms = set([
            word for word in recent_user_text.split() 
            if len(word) > 2 and word not in stop_words
        ])
        
        # Calculate overlap (Jaccard similarity)
        if not goal_terms or not user_terms:
            jaccard_similarity = 0.2  # Low relevance if no meaningful terms
        else:
            overlap = len(goal_terms & user_terms)
            total_unique = len(goal_terms | user_terms)
            jaccard_similarity = overlap / total_unique if total_unique > 0 else 0
        
        # Semantic keyword matching for common topic categories
        semantic_match = 0.0
        
        # Hobby/leisure category
        hobby_keywords = ["hobby", "hobbies", "interest", "interests", "enjoy", "fun", "leisure", 
                         "recreation", "play", "playing", "chess", "guitar", "poetry", "music", 
                         "art", "creative", "creative", "hobby", "pastime"]
        hobby_goal_keywords = hobby_keywords + ["explore", "discover", "practice", "master", "learn"]
        
        # Work/professional category  
        work_keywords = ["work", "job", "career", "professional", "project", "task", "business",
                        "workplace", "office", "client", "meeting", "deadline"]
        work_goal_keywords = work_keywords + ["develop", "build", "create", "improve", "enhance"]
        
        # Learning/education category
        learning_keywords = ["learn", "study", "understand", "master", "skill", "knowledge", 
                            "education", "course", "lesson", "tutorial"]
        
        # Check for hobby context
        if any(kw in recent_user_text for kw in hobby_keywords):
            if any(kw in goal_text for kw in hobby_goal_keywords):
                semantic_match = 0.7  # Strong match
            elif any(kw in goal_text for kw in ["explore", "discover", "play", "practice", "master"]):
                semantic_match = 0.5  # Moderate match
        
        # Check for work context
        elif any(kw in recent_user_text for kw in work_keywords):
            if any(kw in goal_text for kw in work_goal_keywords):
                semantic_match = 0.7  # Strong match
            elif any(kw in goal_text for kw in ["develop", "build", "create", "improve"]):
                semantic_match = 0.5  # Moderate match
        
        # Check for learning context (less specific, so lower weight)
        if any(kw in recent_user_text for kw in learning_keywords):
            if any(kw in goal_text for kw in learning_keywords):
                semantic_match = max(semantic_match, 0.4)  # Moderate match
        
        # Check conversational themes if available
        theme_match = 0.0
        if schema and schema.conversational_themes:
            # Safely extract theme_seed (defensive against schema changes)
            recent_themes = []
            for t in schema.conversational_themes[-3:]:  # Last 3 themes
                theme_text_val = getattr(t, 'theme_seed', None) or getattr(t, 'theme', None)
                if theme_text_val:
                    recent_themes.append(str(theme_text_val).lower())
            theme_text = " ".join(recent_themes).lower()
            if theme_text:
                # Check if goal mentions any recent theme keywords
                theme_words = set([w for w in theme_text.split() if len(w) > 3 and w not in stop_words])
                goal_words = set([w for w in goal_text.split() if len(w) > 3 and w not in stop_words])
                if theme_words and goal_words:
                    theme_overlap = len(theme_words & goal_words)
                    theme_match = min(0.5, theme_overlap / max(len(theme_words), len(goal_words)))
        
        # Combine all signals: jaccard (40%), semantic (40%), theme (20%)
        relevance = min(1.0, jaccard_similarity * 0.4 + semantic_match * 0.4 + theme_match * 0.2)
        
        print(f"[GOAL_DISCOVERY] Relevance check for '{goal.goal}': {relevance:.2f} (jaccard={jaccard_similarity:.2f}, semantic={semantic_match:.2f}, theme={theme_match:.2f})")
        return relevance

    def _check_goal_readiness(
        self, 
        schema: DiscoverySchema,
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Check if any goal candidate is ready for confirmation.

        Uses explicit dimension criteria rather than LLM-determined readiness.
        Skips previously rejected AND accepted goals.
        Prioritizes goals that are relevant to recent conversation context.

        Args:
            schema: Current discovery schema
            conversation_history: Recent conversation history for relevance checking

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
        
        # Check relevance for each goal if we have conversation history
        goals_with_relevance = []
        for goal in sorted_goals:
            # Skip already-rejected goals
            if goal.id in rejected_ids:
                print(f"[GOAL_DISCOVERY] Skipping rejected goal: '{goal.goal}'")
                continue
            
            # Skip already-accepted goals (don't re-propose)
            if goal.id in accepted_ids:
                print(f"[GOAL_DISCOVERY] Skipping already-accepted goal: '{goal.goal}'")
                continue
            
            # Calculate relevance to recent conversation
            relevance = 0.5  # Default neutral relevance
            if conversation_history:
                relevance = self._check_goal_relevance(goal, conversation_history, schema)
            
            goals_with_relevance.append((goal, goal_score(goal), relevance))
        
        # Sort by combined score: readiness score + relevance boost
        # Relevance acts as a multiplier - highly relevant goals get prioritized
        def combined_score(item):
            goal, base_score, relevance = item
            # Boost relevant goals: multiply base score by (1 + relevance)
            # This means a goal with 0.7 base score and 0.8 relevance gets 0.7 * 1.8 = 1.26
            # While a goal with 0.7 base score and 0.3 relevance gets 0.7 * 1.3 = 0.91
            return base_score * (1.0 + relevance * 0.5)  # Relevance contributes up to 50% boost
        
        goals_with_relevance.sort(key=combined_score, reverse=True)
        
        # Try each goal in order of combined score (relevance is used for PRIORITIZATION, not filtering)
        for goal, base_score, relevance in goals_with_relevance:
            ready, reason = self._is_goal_ready(goal)
            print(f"[GOAL_DISCOVERY] Goal '{goal.goal}': ready={ready}, reason={reason}, relevance={relevance:.2f}")
            print(f"[GOAL_DISCOVERY]   concreteness={goal.concreteness:.2f}, break_apartability={goal.break_apartability:.2f}")
            print(f"[GOAL_DISCOVERY]   scope_appropriateness={goal.scope_appropriateness:.2f}, user_commitment={goal.user_commitment:.2f}")
            
            # If goal is ready (based on dimensions), propose it
            # Relevance is only used for sorting/prioritization, not as a filter
            # The cooldown check (below) handles preventing proposals during normal conversation
            if ready:
                print(f"[GOAL_DISCOVERY] Proposing goal '{goal.goal}' (ready={ready}, relevance={relevance:.2f})")
                return {"ready": True, "best_goal": goal}
        
        # No ready goals found
        if goals_with_relevance:
            best_goal, best_score, best_relevance = goals_with_relevance[0]
            best_ready, best_reason = self._is_goal_ready(best_goal)
            print(f"[GOAL_DISCOVERY] No ready goals. Best candidate: '{best_goal.goal}' (score={best_score:.2f}, relevance={best_relevance:.2f}, ready={best_ready}, reason={best_reason})")
        
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

            # Wait for Phase 1 to complete with individual timing
            branch_start = time.time()
            branch_condition = future_branch.result()
            print(f"[TIMING] Branch classification completed in {time.time() - branch_start:.2f}s")
            
            if future_profile:
                profile_start = time.time()
                profile_updates = future_profile.result()
                print(f"[TIMING] Profile update completed in {time.time() - profile_start:.2f}s")
            else:
                profile_updates = None
            
            if future_themes:
                themes_start = time.time()
                theme_updates = future_themes.result()
                print(f"[TIMING] Themes update completed in {time.time() - themes_start:.2f}s")
            else:
                theme_updates = None

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

        print(f"[TIMING] Starting goal_candidates LLM call...")
        goal_updates = self._update_goal_candidates(
            temp_schema,  # Now has fresh themes!
            conversation_history,
            current_schema.interview_state.turns_elapsed + 1
        )
        print(f"[TIMING] goal_candidates LLM call completed in {time.time() - phase2_start:.2f}s")

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
        
        # COOLDOWN AFTER REJECTING A GOAL: Require at least 3 turns of exploration before proposing another
        # This prevents the system from immediately proposing goals during normal conversation
        goal_rejection_cooldown = 3
        last_rejected_turn = current_schema.interview_state.last_goal_rejected_turn
        turns_since_rejection = (current_turn - last_rejected_turn) if last_rejected_turn is not None else float('inf')
        
        if current_turn < min_turns_for_goal:
            print(f"[GOAL_DISCOVERY] Too early to propose goal (turn {current_turn} < {min_turns_for_goal})")
            goal_readiness = {"ready": False, "best_goal": None}
        elif turns_since_acceptance < goal_acceptance_cooldown:
            print(f"[GOAL_DISCOVERY] In cooldown after goal acceptance ({turns_since_acceptance} < {goal_acceptance_cooldown} turns)")
            print(f"[GOAL_DISCOVERY] Will explore new threads before proposing another goal")
            goal_readiness = {"ready": False, "best_goal": None}
        elif turns_since_rejection < goal_rejection_cooldown:
            print(f"[GOAL_DISCOVERY] In cooldown after goal rejection ({turns_since_rejection} < {goal_rejection_cooldown} turns)")
            print(f"[GOAL_DISCOVERY] Will continue exploring before proposing another goal")
            goal_readiness = {"ready": False, "best_goal": None}
        else:
            goal_readiness = self._check_goal_readiness(temp_schema, conversation_history)
        
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
        print(f"[TIMING] Starting controller LLM call...")
        controller_dict = self._generate_controller(temp_schema, branch_condition, user_message)
        print(f"[TIMING] Controller LLM call completed in {time.time() - phase3_start:.2f}s")
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

