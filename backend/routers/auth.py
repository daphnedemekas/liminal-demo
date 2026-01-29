"""Authentication and user data endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Union

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    onboarding_info: Optional[str] = None


class LoginResponse(BaseModel):
    user_id: str
    username: str
    is_new_user: bool
    onboarding_info: Optional[str] = None


class GoalResponse(BaseModel):
    id: int
    goal_text: str
    created_at: Optional[str]
    status: str
    has_teaching_candidate: bool
    teaching_candidate: Optional[Union[dict, List[dict]]] = None


class UserDataResponse(BaseModel):
    user_id: str
    username: str
    onboarding_info: Optional[str]
    goals: List[GoalResponse]
    exploration_session: Optional[dict]


class CreateGoalRequest(BaseModel):
    user_id: str
    goal_text: str


class CreateGoalResponse(BaseModel):
    id: int
    goal_text: str


class ResumeSessionRequest(BaseModel):
    user_id: str
    goal_id: Optional[int] = None


class ResumeSessionResponse(BaseModel):
    session_id: str
    conversation_history: list
    is_new: bool
    schema_state: Optional[dict] = None


class SaveSummaryRequest(BaseModel):
    session_id: str
    summary: str


class ProfileSummaryRequest(BaseModel):
    profile_schema: dict = Field(..., alias="schema")
    session_id: Optional[str] = None

    model_config = {"populate_by_name": True}

    @property
    def schema(self) -> dict:
        return self.profile_schema


# Database instance will be injected
_db = None


def init_router(db):
    """Initialize router with database instance."""
    global _db
    _db = db


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login with username (creates account if doesn't exist)."""
    try:
        user = _db.get_user_by_username(request.username)

        if user:
            return LoginResponse(
                user_id=user.user_id,
                username=user.username,
                is_new_user=False,
                onboarding_info=user.onboarding_info
            )
        else:
            user = _db.create_user_with_username(
                request.username,
                request.onboarding_info or ""
            )
            return LoginResponse(
                user_id=user.user_id,
                username=user.username,
                is_new_user=True,
                onboarding_info=user.onboarding_info
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/goal/{goal_id}")
async def update_goal(goal_id: int, body: dict):
    """Update goal text."""
    try:
        goal_text = body.get("goal_text")
        if goal_text:
            _db.update_goal_text(goal_id, goal_text)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}/data", response_model=UserDataResponse)
async def get_user_data(user_id: str):
    """Get all user data including goals and exploration session."""
    try:
        user = _db.get_or_create_user(user_id)
        goals = _db.get_user_goals(user_id)
        exploration = _db.get_user_exploration_session(user_id)

        # Auto-backfill teaching candidates from sessions if missing
        needs_reload = False
        for goal in goals:
            if goal.get("has_teaching_candidate"):
                continue
            try:
                sessions = _db.list_sessions_for_goal(goal["id"])
                teaching_sessions = [s for s in sessions if s.get("session_type") == "teaching" and s.get("teaching_candidate_id")]
                if not teaching_sessions:
                    continue
                candidates = []
                seen_ids = set()
                for ts in teaching_sessions:
                    tc_id = ts.get("teaching_candidate_id")
                    if tc_id in seen_ids:
                        continue
                    seen_ids.add(tc_id)
                    schema = ts.get("schema_state") or {}
                    tc_data = schema.get("teaching_candidate") or {}
                    candidates.append({
                        "id": tc_id,
                        "topic": tc_data.get("topic") or f"Deep dive {tc_id}",
                        "focus_question": tc_data.get("focus_question") or "",
                        "identified_gap": tc_data.get("identified_gap") or "",
                        "status": "available",
                    })
                if candidates:
                    _db.set_goal_teaching_candidates(goal["id"], candidates)
                    needs_reload = True
                    print(f"[Backfill] Goal {goal['id']}: recovered {len(candidates)} teaching candidates from sessions")
            except Exception as e:
                print(f"[Backfill] Error for goal {goal['id']}: {e}")

        if needs_reload:
            goals = _db.get_user_goals(user_id)

        return UserDataResponse(
            user_id=user.user_id,
            username=user.username or "",
            onboarding_info=user.onboarding_info,
            goals=[GoalResponse(**g) for g in goals],
            exploration_session=exploration
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/{user_id}/backfill-teaching-candidates")
async def backfill_teaching_candidates(user_id: str):
    """Backfill teaching candidates from conversation sessions for all goals that are missing them."""
    try:
        goals = _db.get_user_goals(user_id)
        backfilled = 0
        for goal in goals:
            if goal.get("has_teaching_candidate"):
                continue
            # Check if there are teaching sessions for this goal
            sessions = _db.list_sessions_for_goal(goal["id"])
            teaching_sessions = [s for s in sessions if s.get("session_type") == "teaching" and s.get("teaching_candidate_id")]
            if not teaching_sessions:
                continue
            # Extract candidate info from schema_state
            candidates = []
            seen_ids = set()
            for ts in teaching_sessions:
                tc_id = ts.get("teaching_candidate_id")
                if tc_id in seen_ids:
                    continue
                seen_ids.add(tc_id)
                schema = ts.get("schema_state") or {}
                tc_data = schema.get("teaching_candidate") or {}
                candidates.append({
                    "id": tc_id,
                    "topic": tc_data.get("topic") or f"Deep dive {tc_id}",
                    "focus_question": tc_data.get("focus_question") or "",
                    "identified_gap": tc_data.get("identified_gap") or "",
                    "status": "available",
                })
            if candidates:
                _db.set_goal_teaching_candidates(goal["id"], candidates)
                backfilled += 1
                print(f"[Backfill] Goal {goal['id']}: saved {len(candidates)} candidates")
        return {"success": True, "goals_backfilled": backfilled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaveTeachingCandidatesRequest(BaseModel):
    goal_id: int
    teaching_candidates: List[dict]


@router.post("/user/goals/teaching-candidates")
async def save_teaching_candidates(request: SaveTeachingCandidatesRequest):
    """Save teaching candidates for a goal (merges with existing, deduplicates by id)."""
    try:
        goal = _db.get_goal_by_id(request.goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        existing = goal.get("teaching_candidate") or []
        if not isinstance(existing, list):
            existing = [existing] if existing else []

        existing_ids = {tc.get("id") for tc in existing}
        for tc in request.teaching_candidates:
            if tc.get("id") not in existing_ids:
                existing.append(tc)
                existing_ids.add(tc.get("id"))

        _db.set_goal_teaching_candidates(request.goal_id, existing)
        return {"success": True, "count": len(existing)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/goals", response_model=CreateGoalResponse)
async def create_goal(request: CreateGoalRequest):
    """Create a new goal for user."""
    try:
        goal = _db.create_goal(request.user_id, request.goal_text)
        try:
            _db.initialize_goal_panels(goal.id, request.user_id)
            print(f"[CreateGoal] Initialized panels for goal {goal.id}")
        except Exception as panel_err:
            print(f"[CreateGoal] Warning: Failed to initialize panels: {panel_err}")
        return CreateGoalResponse(
            id=goal.id,
            goal_text=goal.goal_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/user/{user_id}/onboarding")
async def update_onboarding(user_id: str, onboarding_info: str):
    """Update user's onboarding info."""
    try:
        _db.update_user_onboarding(user_id, onboarding_info)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/resume", response_model=ResumeSessionResponse)
async def resume_session(request: ResumeSessionRequest):
    """Resume an existing session or create new one for user."""
    try:
        if request.goal_id:
            existing = _db.get_session_for_goal(request.goal_id)
            if existing:
                return ResumeSessionResponse(
                    session_id=existing["session_id"],
                    conversation_history=existing["conversation_history"],
                    is_new=False,
                    schema_state=existing["schema_state"]
                )
            return ResumeSessionResponse(
                session_id="",
                conversation_history=[],
                is_new=True,
                schema_state=None
            )
        else:
            session_data = _db.get_or_create_exploration_session(request.user_id)
            return ResumeSessionResponse(
                session_id=session_data["session_id"],
                conversation_history=session_data["conversation_history"],
                is_new=session_data["is_new"],
                schema_state=session_data["schema_state"]
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/summary/save")
async def save_profile_summary(request: SaveSummaryRequest):
    """Save the LLM-generated profile summary for a session."""
    try:
        _db.save_profile_summary(request.session_id, request.summary)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/reasoning")
async def generate_ai_reasoning(request: ProfileSummaryRequest):
    """Generate the AI tutor's inner monologue / chain of thought reasoning."""
    try:
        from src.llm_client import LLMClient

        schema = request.schema
        session_id = getattr(request, 'session_id', None) or schema.get("session_id")

        conversation_text = ""
        if session_id:
            try:
                history = _db.get_conversation_history(session_id)
                if history:
                    recent = history[-4:] if len(history) > 4 else history
                    conversation_text = "\n".join([
                        f"{'User' if msg['role'] == 'user' else 'AI'}: {msg['content'][:300]}..."
                        if len(msg['content']) > 300 else f"{'User' if msg['role'] == 'user' else 'AI'}: {msg['content']}"
                        for msg in recent
                    ])
            except Exception as e:
                print(f"[Reasoning] Could not fetch conversation: {e}")

        controller = schema.get("controller", {})
        prior_knowledge = schema.get("prior_knowledge_assessment", {})
        goals = schema.get("goal_candidates", [])
        themes = schema.get("conversational_themes", [])
        interview_state = schema.get("interview_state", {})
        scope_goal = interview_state.get("user_goal")
        scope_line = (
            f"Scope: Current learning path is '{scope_goal}'. Focus on this path and its conversation context."
            if scope_goal
            else "Scope: Exploration session. Focus on them broadly across interests (not any single path)."
        )

        context_parts = []

        if conversation_text:
            context_parts.append(f"Recent conversation:\n{conversation_text}")

        if prior_knowledge.get("assessed_level"):
            context_parts.append(f"Assessed knowledge level: {prior_knowledge['assessed_level']}")

        if goals:
            top_goals = [g.get("goal", "") for g in goals[:2] if g.get("goal")]
            if top_goals:
                context_parts.append(f"Emerging goals: {'; '.join(top_goals)}")

        if themes:
            theme_names = [t.get("theme_seed", "") for t in themes[:3] if t.get("theme_seed")]
            if theme_names:
                context_parts.append(f"Topics of interest: {', '.join(theme_names)}")

        if not context_parts:
            return {"reasoning": "Getting to know them..."}

        llm = LLMClient()
        prompt = f"""You are an AI tutor. Write your INNER MONOLOGUE - your private thoughts about advancing this person's learning goal. Write in first person, as if thinking to yourself.

{chr(10).join(context_parts)}

{scope_line}

RULES:
- Write 2-3 sentences of factual inner monologue
- First person, present tense ("I notice...", "I'm considering...", "I should...")
- Be specific to what the user actually said - reference their actual words/interests
- Focus on: what you learned about their understanding, what gaps exist, what to explore next to advance their learning goal
- NO praise, NO emotional language, NO subjective judgments
- FORBIDDEN: "impressed", "interesting", "fascinating", "great", "cool", "exciting", "amazing"
- Be neutral and factual - focus on learning progress, not evaluation
- Maximum 50 words

Example: "They mentioned balancing analytical and creative work. Their background in ML provides foundations for the learning loop design topic. I should probe what specific outcomes they envision to identify the next teaching target."

Write the inner monologue:"""

        reasoning = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model="openai:gpt-4o-mini",
            max_tokens=120
        )

        return {"reasoning": reasoning.strip()}
    except Exception as e:
        print(f"[API] Error generating reasoning: {e}")
        return {"reasoning": "Processing the conversation..."}


@router.post("/profile/summary")
async def generate_profile_summary(request: ProfileSummaryRequest):
    """Generate an LLM summary of the user's profile."""
    try:
        from src.llm_client import LLMClient

        schema = request.schema
        profile = schema.get("user_profile", {})
        goals = schema.get("goal_candidates", [])
        themes = schema.get("conversational_themes", [])
        interview_state = schema.get("interview_state", {})
        scope_goal = interview_state.get("user_goal")
        scope_line = (
            f"Scope: This is their current understanding on their path to '{scope_goal}'."
            if scope_goal
            else "Scope: This is their current understanding across exploration topics (not tied to a single path)."
        )

        context_parts = []

        if profile.get("curiosity_type", {}).get("value"):
            context_parts.append(f"Curiosity type: {profile['curiosity_type']['value']}")

        entry_mode = profile.get("entry_mode", {})
        if entry_mode:
            dominant = max(entry_mode.items(), key=lambda x: x[1] if x[1] else 0)
            if dominant[1] and dominant[1] > 0.3:
                context_parts.append(f"Entry preference: {dominant[0]}-oriented")

        if profile.get("uncertainty_tolerance", {}).get("value"):
            context_parts.append(f"Uncertainty tolerance: {profile['uncertainty_tolerance']['value']}")

        if profile.get("pacing_preference", {}).get("value"):
            pacing = profile['pacing_preference']['value']
            context_parts.append(f"Pacing: {pacing}")

        motivation = profile.get("motivation_profile", {})
        if motivation:
            strong_motivators = [k.replace("_value", "") for k, v in motivation.items() if v and v > 0.5]
            if strong_motivators:
                context_parts.append(f"Key motivators: {', '.join(strong_motivators)}")

        if interview_state.get("user_goal"):
            context_parts.append(f"Confirmed goal: {interview_state['user_goal']}")
        elif goals:
            goal_texts = [g.get("goal", "") for g in goals[:2] if g.get("goal")]
            if goal_texts:
                context_parts.append(f"Exploring goals: {'; '.join(goal_texts)}")

        if themes:
            theme_seeds = [t.get("theme_seed", "") for t in themes[:3] if t.get("theme_seed")]
            if theme_seeds:
                if scope_goal:
                    goal_keywords = scope_goal.lower().split()
                    relevant_themes = [
                        theme for theme in theme_seeds
                        if any(keyword in theme.lower() for keyword in goal_keywords) or len(goal_keywords) == 0
                    ]
                    if relevant_themes:
                        context_parts.append(f"Topics (goal-specific): {', '.join(relevant_themes)}")
                else:
                    context_parts.append(f"Topics: {', '.join(theme_seeds)}")

        if not context_parts:
            return {"summary": "Continue the conversation to build your profile."}

        llm = LLMClient()

        goal_focus_instruction = ""
        if scope_goal:
            goal_focus_instruction = f"\nCRITICAL: Focus ONLY on traits and understanding relevant to the learning goal '{scope_goal}'. Do NOT mention general interests, skills, or topics that are not directly related to this specific goal."

        prompt = f"""Write a VERY SHORT summary (2-3 sentences max, under 80 words total) of their style.

Profile data:
{chr(10).join(f"- {p}" for p in context_parts)}

{scope_line}{goal_focus_instruction}

RULES:
- Maximum 80 words
- Plain text only, no markdown or formatting
- Be direct and factual
- Focus on 1-2 key traits, not all of them
- No praise or flowery language
- If a specific learning goal is mentioned, ONLY discuss traits and understanding relevant to that goal

Example good output (for a goal): "You approach chess endgames with a methodical, pattern-recognition style. Your high tolerance for uncertainty helps you explore complex positions without needing immediate resolution."

Example good output (for exploration): "You show interest-driven curiosity, meaning you learn for the pleasure of understanding rather than to fill knowledge gaps. Combined with your high tolerance for uncertainty, you're well-suited for open-ended exploration of complex topics."

Write the summary now:"""

        summary = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model="openai:gpt-4o-mini"
        )

        return {"summary": summary.strip()}
    except Exception as e:
        print(f"[Profile Summary] Error: {e}")
        return {"summary": "Profile analysis in progress..."}
