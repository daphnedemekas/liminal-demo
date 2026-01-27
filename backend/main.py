"""FastAPI application for Liminal Discovery System."""
import sys
from pathlib import Path

# Load environment variables from .env file (only if it exists, for local development)
# In Railway, environment variables are set directly, so this won't override them
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)  # Don't override existing env vars (Railway's)
else:
    # In Railway/production, just load from environment
    load_dotenv(override=False)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
import uuid
import os

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.services.session_manager import session_manager
from backend.services.audio_service import get_audio_service
from backend.models.api_models import (
    SessionCreateRequest,
    SessionCreateResponse,
    TopicFoundResponse
)

app = FastAPI(title="Liminal Discovery API")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for serving audio
audio_service = get_audio_service()
app.mount("/audio", StaticFiles(directory=str(audio_service.audio_dir)), name="audio")

# Store frontend path for later (will be mounted after all API routes)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"


# ============================================
# User Authentication & Data Endpoints
# ============================================

from src.database.manager import DatabaseManager
from pydantic import BaseModel, Field
from typing import Optional, List, Union

# Initialize database - using SQLite
db_path = os.getenv("DATABASE_PATH", "data/liminal.db")
print(f"[Backend] Initializing SQLite database at {db_path}...")
db = DatabaseManager(db_path=db_path)
print(f"[Backend] Database initialized successfully")

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
    teaching_candidate: Optional[Union[dict, List[dict]]] = None  # Single candidate or list of curriculum tasks

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


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login with username (creates account if doesn't exist)."""
    try:
        # Check if user exists
        user = db.get_user_by_username(request.username)
        
        if user:
            return LoginResponse(
                user_id=user.user_id,
                username=user.username,
                is_new_user=False,
                onboarding_info=user.onboarding_info
            )
        else:
            # Create new user
            user = db.create_user_with_username(
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


@app.get("/api/user/{user_id}/data", response_model=UserDataResponse)
async def get_user_data(user_id: str):
    """Get all user data including goals and exploration session."""
    try:
        user = db.get_or_create_user(user_id)
        goals = db.get_user_goals(user_id)
        exploration = db.get_user_exploration_session(user_id)
        
        return UserDataResponse(
            user_id=user.user_id,
            username=user.username or "",
            onboarding_info=user.onboarding_info,
            goals=[GoalResponse(**g) for g in goals],
            exploration_session=exploration
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/goals", response_model=CreateGoalResponse)
async def create_goal(request: CreateGoalRequest):
    """Create a new goal for user."""
    try:
        goal = db.create_goal(request.user_id, request.goal_text)
        # Initialize default panels (channels) for the new goal
        try:
            db.initialize_goal_panels(goal.id, request.user_id)
            print(f"[CreateGoal] Initialized panels for goal {goal.id}")
        except Exception as panel_err:
            print(f"[CreateGoal] Warning: Failed to initialize panels: {panel_err}")
            # Don't fail goal creation if panel init fails
        return CreateGoalResponse(
            id=goal.id,
            goal_text=goal.goal_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/user/{user_id}/onboarding")
async def update_onboarding(user_id: str, onboarding_info: str):
    """Update user's onboarding info."""
    try:
        db.update_user_onboarding(user_id, onboarding_info)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProfileSummaryRequest(BaseModel):
    profile_schema: dict = Field(..., alias="schema")  # API uses "schema", internal name avoids shadowing
    session_id: Optional[str] = None
    
    model_config = {"populate_by_name": True}  # Allow both field name and alias
    
    @property
    def schema(self) -> dict:
        """Backward compatibility: access schema via .schema property"""
        return self.profile_schema


# ============================================
# Session Resume Endpoints
# ============================================

class ResumeSessionRequest(BaseModel):
    user_id: str
    goal_id: Optional[int] = None  # If resuming a goal session

class ResumeSessionResponse(BaseModel):
    session_id: str
    conversation_history: list
    is_new: bool
    schema_state: Optional[dict] = None


@app.post("/api/session/resume", response_model=ResumeSessionResponse)
async def resume_session(request: ResumeSessionRequest):
    """Resume an existing session or create new one for user."""
    try:
        if request.goal_id:
            # Try to get existing goal session
            existing = db.get_session_for_goal(request.goal_id)
            if existing:
                return ResumeSessionResponse(
                    session_id=existing["session_id"],
                    conversation_history=existing["conversation_history"],
                    is_new=False,
                    schema_state=existing["schema_state"]
                )
            # No existing session for this goal - will need to create one via /start
            return ResumeSessionResponse(
                session_id="",
                conversation_history=[],
                is_new=True,
                schema_state=None
            )
        else:
            # Get or create exploration session
            session_data = db.get_or_create_exploration_session(request.user_id)
            return ResumeSessionResponse(
                session_id=session_data["session_id"],
                conversation_history=session_data["conversation_history"],
                is_new=session_data["is_new"],
                schema_state=session_data["schema_state"]
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaveSummaryRequest(BaseModel):
    session_id: str
    summary: str


@app.post("/api/profile/summary/save")
async def save_profile_summary(request: SaveSummaryRequest):
    """Save the LLM-generated profile summary for a session."""
    try:
        db.save_profile_summary(request.session_id, request.summary)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/reasoning")
async def generate_ai_reasoning(request: ProfileSummaryRequest):
    """Generate the AI tutor's inner monologue / chain of thought reasoning."""
    try:
        from src.llm_client import LLMClient
        
        schema = request.schema
        session_id = getattr(request, 'session_id', None) or schema.get("session_id")
        
        # Fetch actual conversation history if we have session_id
        conversation_text = ""
        if session_id:
            try:
                history = db.get_conversation_history(session_id)
                if history:
                    # Format last few exchanges (up to 4 messages)
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
            else "Scope: Exploration session. Focus on the learner broadly across interests (not any single path)."
        )
        
        # Build context
        context_parts = []
        
        # Add actual conversation
        if conversation_text:
            context_parts.append(f"Recent conversation:\n{conversation_text}")
        
        # Add schema insights
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
            return {"reasoning": "Getting to know this learner..."}
        
        # Generate inner monologue with LLM
        llm = LLMClient()
        prompt = f"""You are an AI tutor. Write your INNER MONOLOGUE - your private thoughts about advancing this learner's learning goal. Write in first person, as if thinking to yourself.

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


@app.post("/api/profile/summary")
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
            f"Scope: This is the learner's current understanding on their path to '{scope_goal}'."
            if scope_goal
            else "Scope: This is the learner's current understanding across exploration topics (not tied to a single path)."
        )
        
        # Build a concise context for the LLM
        context_parts = []
        
        # Add profile info
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
        
        # Add goal info
        if interview_state.get("user_goal"):
            context_parts.append(f"Confirmed goal: {interview_state['user_goal']}")
        elif goals:
            goal_texts = [g.get("goal", "") for g in goals[:2] if g.get("goal")]
            if goal_texts:
                context_parts.append(f"Exploring goals: {'; '.join(goal_texts)}")
        
        # Add themes - filter to goal-relevant if we have a specific goal
        if themes:
            theme_seeds = [t.get("theme_seed", "") for t in themes[:3] if t.get("theme_seed")]
            if theme_seeds:
                # If we have a specific goal, only include themes that are relevant to that goal
                if scope_goal:
                    # Filter themes to only those relevant to the current goal
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
            return {"summary": "Continue the conversation to build your learner profile."}
        
        # Generate summary with LLM
        llm = LLMClient()
        
        # Add explicit instruction to focus on goal if we have one
        goal_focus_instruction = ""
        if scope_goal:
            goal_focus_instruction = f"\nCRITICAL: Focus ONLY on traits and understanding relevant to the learning goal '{scope_goal}'. Do NOT mention general interests, skills, or topics that are not directly related to this specific goal."
        
        prompt = f"""Write a VERY SHORT summary (2-3 sentences max, under 80 words total) of this learner's style.

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


@app.get("/api/trajectory/{user_id}")
async def get_trajectory(user_id: str):
    """Get (or initialize) the user's cross-phase learner trajectory dashboard JSON."""
    try:
        traj = db.get_or_create_learner_trajectory(user_id)
        return traj.get("dashboard_state") or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trajectory/{user_id}/refresh")
async def refresh_trajectory(user_id: str):
    """Incrementally refresh the user's trajectory dashboard from new checkpoints."""
    try:
        from src.agents.trajectory_updater import TrajectoryUpdater

        updater = TrajectoryUpdater(db=db)
        dashboard = updater.refresh(user_id=user_id)
        return dashboard
    except Exception as e:
        import traceback
        print(f"[Trajectory Refresh Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goal/{goal_id}/progress")
async def get_goal_progress(goal_id: int, user_id: str):
    """
    Get detailed progress data for a specific goal.

    Returns goal metadata, teaching sessions, and temporal metrics.
    """
    try:
        # Get goal
        goal = db.get_goal_by_id(goal_id)
        if not goal or goal.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Get all sessions for this goal
        sessions = db.list_sessions_for_goal(goal_id)
        
        # Filter to only teaching sessions for the sessions list
        teaching_sessions = [s for s in sessions if s.get("session_type") == "teaching"]
        
        # Get curriculum from goal if available
        teaching_candidate_data = goal.get("teaching_candidate")
        curriculum_tasks = None
        
        if isinstance(teaching_candidate_data, list) and len(teaching_candidate_data) > 0:
            # Preserve original order by sorting by id (tasks should have id field from curriculum proposal)
            curriculum_tasks = sorted(teaching_candidate_data, key=lambda x: x.get('id', x.get('index', 0)))
        elif isinstance(teaching_candidate_data, dict):
            # Handle case where it might be a single object instead of array
            curriculum_tasks = [teaching_candidate_data]
        
        # Debug logging
        print(f"[Goal Progress] Goal {goal_id}: teaching_sessions={len(teaching_sessions)}, curriculum_tasks={len(curriculum_tasks) if curriculum_tasks else 0}")
        print(f"[Goal Progress] teaching_candidate type: {type(teaching_candidate_data)}, value: {teaching_candidate_data}")
        if curriculum_tasks:
            print(f"[Goal Progress] Curriculum tasks: {[t.get('topic', t.get('title', t.get('justification', 'Unknown'))) for t in curriculum_tasks[:3]]}")

        # Get checkpoints for temporal data
        checkpoints = []
        for session in sessions:
            session_checkpoints = db.list_trajectory_checkpoints_for_session(session["session_id"])
            # Add session_id to each checkpoint for filtering
            for cp in session_checkpoints:
                cp["session_id"] = session["session_id"]
            checkpoints.extend(session_checkpoints)

        # Sort by timestamp
        checkpoints.sort(key=lambda x: x.get("created_at") or "")

        # Extract temporal metrics
        temporal_data = []
        for cp in checkpoints:
            metrics = cp.get("metrics", {})
            temporal_data.append({
                "session_id": cp.get("session_id"),
                "timestamp": cp.get("created_at"),
                "turn": cp.get("turn_index"),
                "foundational_understanding": metrics.get("foundational_understanding", 0),
                "applied_mastery": metrics.get("applied_mastery", 0),
                "metacognitive_awareness": metrics.get("metacognitive_awareness", 0),
                "teaching_steps_completed": metrics.get("teaching_steps_completed", 0),
                "teaching_steps_total": metrics.get("teaching_steps_total", 0)
            })

        # Compute current progress
        total_sessions = len(teaching_sessions)
        completed_sessions = sum(1 for s in teaching_sessions if s.get("status") == "completed")
        progress_pct = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0

        return {
            "goal": goal,
            "sessions": teaching_sessions,  # Only teaching sessions
            "curriculum": curriculum_tasks,  # Curriculum tasks if available
            "progress_percentage": progress_pct,
            "temporal_data": temporal_data,
            "current_metrics": temporal_data[-1] if temporal_data else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/teaching/{session_id}/detail")
async def get_teaching_detail(session_id: str, user_id: str):
    """
    Get detailed view of a single teaching session with temporal progress.

    Returns session metadata, curriculum plan, and understanding marker progression.
    """
    try:
        # Get session
        session = db.get_session_by_id(session_id)
        if not session or session.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get teaching schema from session
        schema_state = session.get("schema_state", {})
        curriculum_plan = schema_state.get("curriculum_plan", {})
        understanding_markers = schema_state.get("understanding_markers", {})

        # Get all checkpoints for this session
        checkpoints = db.list_trajectory_checkpoints_for_session(session_id)

        # Extract temporal understanding metrics
        timeline = []
        for cp in checkpoints:
            metrics = cp.get("metrics", {})
            timeline.append({
                "turn": cp.get("turn_index"),
                "timestamp": cp.get("created_at"),
                "foundational_understanding": metrics.get("foundational_understanding", 0),
                "applied_mastery": metrics.get("applied_mastery", 0),
                "metacognitive_awareness": metrics.get("metacognitive_awareness", 0)
            })

        # Get latest understanding marker aggregates
        from src.trajectory.metrics import compute_all_aggregates

        # Convert understanding_markers if it's a list to dict format
        if isinstance(understanding_markers, list):
            markers_dict = {}
            for marker in understanding_markers:
                if isinstance(marker, dict) and marker.get("id"):
                    markers_dict[marker["id"]] = marker
            understanding_markers = markers_dict

        current_aggregates = compute_all_aggregates(understanding_markers) if understanding_markers else {
            "foundational_understanding": 0,
            "applied_mastery": 0,
            "metacognitive_awareness": 0
        }

        return {
            "session": session,
            "curriculum_plan": curriculum_plan,
            "understanding_timeline": timeline,
            "current_aggregates": current_aggregates,
            "all_markers": understanding_markers
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Feed Content Endpoints
# ============================================

class FeedRequest(BaseModel):
    user_id: str
    context_type: str  # 'exploration', 'goal', or 'teaching_candidate'
    goal_id: Optional[int] = None
    goal_text: Optional[str] = None
    teaching_candidate_id: Optional[str] = None
    teaching_topic: Optional[str] = None
    user_background: Optional[str] = None
    goals_summary: Optional[str] = None  # For exploration feed - summary of all goals

class FeedItemResponse(BaseModel):
    id: int
    title: str
    content: str
    source_citation: Optional[str]
    source_url: Optional[str]
    relevance_note: Optional[str]

class FeedResponse(BaseModel):
    items: List[FeedItemResponse]
    generated: bool  # True if just generated, False if loaded from DB


@app.post("/api/feed", response_model=FeedResponse)
async def get_or_generate_feed(request: FeedRequest):
    """Get feed items for a context, generating if needed."""
    try:
        # Check if feed already exists
        has_feed = db.has_feed_items(
            user_id=request.user_id,
            context_type=request.context_type,
            goal_id=request.goal_id,
            teaching_candidate_id=request.teaching_candidate_id
        )
        
        if has_feed:
            # Return existing feed
            items = db.get_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
            return FeedResponse(
                items=[FeedItemResponse(**item) for item in items],
                generated=False
            )
        
        # Generate new feed
        from src.llm_client import LLMClient
        from pathlib import Path
        
        # Load prompt template
        prompt_path = Path(__file__).parent.parent / "prompts" / "feed" / "generate_feed.txt"
        with open(prompt_path) as f:
            prompt_template = f.read()
        
        # Build context details - only include relevant info for this context type
        context_details = ""
        user_background_for_prompt = request.user_background or "No background provided"
        
        if request.context_type == "exploration":
            context_details = f"User is exploring potential learning directions.\nCurrent interests/goals: {request.goals_summary or 'Still discovering'}"
        elif request.context_type == "goal":
            # For goal context, don't pass general user background - focus only on the goal
            context_details = f"User's learning goal: {request.goal_text}"
            user_background_for_prompt = "Focus ONLY on the learning goal specified above. Ignore any general user background that is not directly relevant to this specific goal."
        elif request.context_type == "teaching_candidate":
            context_details = f"Goal: {request.goal_text}\nSpecific topic: {request.teaching_topic}"
            user_background_for_prompt = "Focus ONLY on the specific teaching topic mentioned above. Ignore any general user background that is not directly relevant to this specific topic."
        
        # Format prompt - only pass fields that are actually used in the template
        # All context-specific info is in context_details, so we don't need separate goal_text/teaching_topic
        prompt = prompt_template.format(
            context_type=request.context_type,
            context_details=context_details,
            user_background=user_background_for_prompt,
            num_items=7
        )
        
        # Generate with LLM - run in executor to avoid blocking, but allow LLM client's retry logic to handle timeouts
        llm = LLMClient()
        response = None
        try:
            loop = asyncio.get_event_loop()
            # Use a longer timeout (180s) to allow for retries, but let LLM client handle its own retries
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: llm.chat_with_json(
                        messages=[{"role": "user", "content": prompt}],
                        model="openai:gpt-4o-mini",
                        json_top_level="array",  # Expecting a list of items
                        max_retries=3  # LLM client will retry on failures
                    )
                ),
                timeout=300.0  # 5 minutes total - allows for 3 retries (90s each) plus buffer
            )
        except asyncio.TimeoutError:
            print(f"[Feed] LLM call timed out after 180s - this is unusual, check API status")
            return FeedResponse(items=[], generated=False)
        except Exception as e:
            print(f"[Feed] Error generating feed: {e}")
            import traceback
            traceback.print_exc()
            return FeedResponse(items=[], generated=False)
        
        if response is None:
            print(f"[Feed] No response from LLM - returning empty feed")
            return FeedResponse(items=[], generated=False)
        
        # Parse response - it should be a list
        if isinstance(response, list):
            items = response
        elif isinstance(response, dict) and "items" in response:
            items = response["items"]
        else:
            print(f"[Feed] Unexpected response format: {type(response)}")
            items = []

        # Validate each item has required fields
        validated_items = []
        for item in items:
            if isinstance(item, dict) and "title" in item and "content" in item:
                validated_items.append(item)
            else:
                print(f"[Feed] Skipping invalid item: {item}")

        items = validated_items

        # Don't save empty feeds - let it retry when there's more conversation
        if not items:
            print(f"[Feed] No items generated - likely not enough conversation yet")
            return FeedResponse(items=[], generated=False)

        # Save to database
        save_successful = False
        if items:
            try:
                db.save_feed_items(
                    user_id=request.user_id,
                    context_type=request.context_type,
                    items=items,
                    goal_id=request.goal_id,
                    teaching_candidate_id=request.teaching_candidate_id
                )
                save_successful = True
            except Exception as e:
                print(f"[Feed] Failed to save items to database: {e}")
                import traceback
                traceback.print_exc()
                # Continue anyway - we can still return the generated items

        # Retrieve saved items (to get IDs) or return generated items if save failed
        if save_successful:
            saved_items = db.get_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
            print(f"[Feed] Retrieved {len(saved_items)} saved items from database")
            try:
                response_items = [FeedItemResponse(**item) for item in saved_items]
                return FeedResponse(
                    items=response_items,
                    generated=True
                )
            except Exception as e:
                print(f"[Feed] Error creating FeedItemResponse from saved items: {e}")
                import traceback
                traceback.print_exc()
                # Fall back to returning generated items directly
                return FeedResponse(
                    items=[FeedItemResponse(id=i, **item) for i, item in enumerate(items)],
                    generated=True
                )
        else:
            # Return generated items directly (without IDs)
            return FeedResponse(
                items=[FeedItemResponse(id=i, **item) for i, item in enumerate(items)],
                generated=True
            )
        
    except Exception as e:
        print(f"[Feed] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/feed/{user_id}/{context_type}")
async def clear_feed(user_id: str, context_type: str, goal_id: Optional[int] = None):
    """Clear feed items to force regeneration."""
    try:
        # This would need a delete method in DB manager
        # For now, just return success (items will be regenerated on next request)
        return {"success": True, "message": "Feed will be regenerated on next request"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Teaching Curriculum Endpoints (Phase 3)
# ============================================

from src.agents.teaching_orchestrator import TeachingOrchestrator

# Store teaching sessions in memory (parallel to discovery sessions)
teaching_sessions: dict = {}


class TeachingStartRequest(BaseModel):
    user_id: str
    goal_id: int
    goal_text: str
    teaching_candidate_id: int
    topic: str
    identified_gap: Optional[str] = ""  # Make optional with default
    focus_question: Optional[str] = ""  # Make optional with default
    goal_conversation_history: list = []  # Context from goal chat
    user_background: str = ""
    current_model_summary: Optional[str] = None
    stakes_summary: Optional[str] = None
    llm_config: Optional[dict] = None  # Model configuration (e.g., {"ranker": "openai:gpt-4o"})


class TeachingStartResponse(BaseModel):
    session_id: str
    opening_message: str
    conversation_history: list = []
    is_resumed: bool = False
    curriculum_plan: Optional[dict] = None
    phase: Optional[str] = None  # e.g., "assessment", "curriculum_proposal", "teaching"
    message_type: Optional[str] = None  # e.g., "assessment_question", "curriculum_proposed"


@app.post("/api/teaching/start", response_model=TeachingStartResponse)
async def start_teaching(request: TeachingStartRequest):
    """
    Initialize or resume a teaching session with curriculum-based learning.
    """
    try:
        # Fetch existing teaching candidates for this goal (for sequential awareness)
        existing_candidates = db.get_teaching_candidates_for_goal(request.goal_id)
        # Exclude the current teaching candidate from the list
        existing_candidates = [c for c in existing_candidates if c.get("id") != request.teaching_candidate_id]
        print(f"[Teaching] Found {len(existing_candidates)} existing teaching candidates for goal {request.goal_id}")
        
        # Check if existing session for this goal + teaching candidate
        existing = db.get_session_for_teaching(request.goal_id, request.teaching_candidate_id)
        
        if existing and existing.get("session_id"):
            # Resume existing teaching session
            session_id = existing["session_id"]
            conversation_history = existing.get("conversation_history", [])
            schema_state = existing.get("schema_state")
            
            print(f"[Teaching] Resuming session: {session_id[:8]}... ({len(conversation_history)} messages)")
            
            # Create orchestrator with restored state
            teaching_candidate = {
                "topic": request.topic,
                "focus_question": request.focus_question,
                "identified_gap": request.identified_gap,
                "current_model_summary": request.current_model_summary,
                "stakes_summary": request.stakes_summary
            }
            
            # Get database path from environment
            db_path = os.getenv("DATABASE_PATH", "data/liminal.db")
            
            orchestrator = TeachingOrchestrator(
                user_id=request.user_id,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id,
                teaching_candidate=teaching_candidate,
                goal_text=request.goal_text,
                user_background=request.user_background,
                goal_conversation_history=request.goal_conversation_history,
                existing_teaching_candidates=existing_candidates,
                db_path=db_path,
                model_config=request.llm_config,
                session_id=session_id,
                conversation_history=conversation_history,
                schema_state=schema_state
            )
            
            # Store in memory
            teaching_sessions[session_id] = orchestrator
            
            return TeachingStartResponse(
                session_id=session_id,
                opening_message="",  # No opening for resumed sessions
                conversation_history=conversation_history,
                is_resumed=True,
                curriculum_plan=orchestrator.schema.curriculum_plan.model_dump() if orchestrator.schema.curriculum_plan else None
            )
        
        # Create new teaching session
        teaching_candidate = {
            "topic": request.topic,
            "focus_question": request.focus_question,
            "identified_gap": request.identified_gap,
            "current_model_summary": request.current_model_summary,
            "stakes_summary": request.stakes_summary
        }
        
        # Get database path from environment
        db_path = os.getenv("DATABASE_PATH", "data/liminal.db")
        
        orchestrator = TeachingOrchestrator(
            user_id=request.user_id,
            goal_id=request.goal_id,
            teaching_candidate_id=request.teaching_candidate_id,
            teaching_candidate=teaching_candidate,
            goal_text=request.goal_text,
            user_background=request.user_background,
            goal_conversation_history=request.goal_conversation_history,
            existing_teaching_candidates=existing_candidates,
            db_path=db_path,
            model_config=request.llm_config
        )
        
        session_id = orchestrator.session_id
        
        # Create DB session entry
        db.create_session_with_type(
            session_id, 
            request.user_id, 
            'teaching', 
            request.goal_id,
            request.teaching_candidate_id
        )
        
        # Generate opening (starts in assessment phase)
        start_result = orchestrator.start()
        
        # Store in memory
        teaching_sessions[session_id] = orchestrator
        
        print(f"[Teaching] Created new session: {session_id[:8]}... for topic: {request.topic} (phase: {start_result.get('phase', 'unknown')})")

        return TeachingStartResponse(
            session_id=session_id,
            opening_message=start_result.get("message", ""),
            conversation_history=orchestrator.conversation_history,
            is_resumed=False,
            curriculum_plan=orchestrator.schema.curriculum_plan.model_dump() if orchestrator.schema.curriculum_plan.steps else None,
            phase=start_result.get("phase"),
            message_type=start_result.get("type")
        )
        
    except Exception as e:
        print(f"[Teaching Start] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/teaching/{session_id}/state")
async def get_teaching_state(session_id: str):
    """Get current teaching state for ProfilePanel display."""
    try:
        # Check in-memory first
        if session_id in teaching_sessions:
            orchestrator = teaching_sessions[session_id]
            return orchestrator.get_schema()
        
        # Try to load from database
        session_data = db.get_session_by_id(session_id)
        if session_data and session_data.get("schema_state"):
            return session_data["schema_state"]
        
        raise HTTPException(status_code=404, detail="Teaching session not found")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Teaching State] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/teaching/{session_id}")
async def teaching_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for teaching curriculum conversation."""
    await websocket.accept()
    
    # Get orchestrator
    orchestrator = teaching_sessions.get(session_id)
    session_info = None
    
    if not orchestrator:
        # Try to restore from database
        session_data = db.get_session_by_id(session_id)
        if session_data and session_data.get("schema_state"):
            # Would need to reconstruct orchestrator - for now, error
            await websocket.send_json({
                "type": "error",
                "message": "Teaching session expired. Please restart from the teaching panel."
            })
            await websocket.close()
            return
        else:
            await websocket.send_json({
                "type": "error", 
                "message": "Teaching session not found"
            })
            await websocket.close()
            return
    
    try:
        # Cache session info for checkpoint attribution
        try:
            session_info = db.get_session_by_id(session_id) or {}
        except Exception:
            session_info = {}

        # Send initial connection confirmation to enable input
        await websocket.send_json({
            "type": "status",
            "status": ""
        })

        def _maybe_checkpoint(teaching_schema: dict):
            """Persist a sparse trajectory checkpoint for this user (best-effort)."""
            try:
                user_id = (teaching_schema or {}).get("user_id") or getattr(orchestrator, "user_id", None)
                if not user_id:
                    return
                db.maybe_write_trajectory_checkpoint(
                    user_id=user_id,
                    session_id=session_id,
                    session_type=session_info.get("session_type") or "teaching",
                    goal_id=session_info.get("goal_id"),
                    teaching_candidate_id=session_info.get("teaching_candidate_id"),
                    schema_state=teaching_schema,
                    conversation_history=getattr(orchestrator, "conversation_history", None),
                    turn_index=(teaching_schema or {}).get("turns_elapsed"),
                )
            except Exception as e:
                print(f"[Trajectory] Teaching checkpoint failed: {e}")

        while True:
            # Receive message from frontend
            data = await websocket.receive_json()
            user_message = data.get("content", "")
            wants_audio = data.get("audio_mode", False) or data.get("audio", False)  # Check if user wants audio

            # Check for special commands (curriculum accept/modify) first
            command = data.get("command")
            if command:
                user_message = command  # Pass command to orchestrator

            # Skip if no message or command
            if not user_message:
                continue

            # Send status
            await websocket.send_json({
                "type": "status",
                "status": "Processing..."
            })

            try:
                
                # Process message through teaching orchestrator
                import asyncio
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    orchestrator.process_user_message,
                    user_message
                )
                
                # Get current state for markers/progress
                schema = orchestrator.get_schema()
                
                # result is now a dict with message, phase, type, etc.
                message_type = result.get("type", "teaching_message")
                message_content = result.get("message", "")
                phase = result.get("phase", "teaching")
                
                # Check if teaching phase is complete
                if orchestrator.is_complete():
                    # Mark this teaching candidate as completed and unlock the next one
                    try:
                        session_info = db.get_session_by_id(session_id)
                        if session_info and session_info.get("goal_id"):
                            goal_id = session_info["goal_id"]
                            # Get teaching_candidate_id from session_info (not schema)
                            teaching_candidate_id = session_info.get("teaching_candidate_id")
                            
                            # Validate that we have the required information
                            if not teaching_candidate_id:
                                print(f"[Teaching] WARNING: No teaching_candidate_id found in session_info for session {session_id}")
                                # Try to get from schema as fallback
                                teaching_candidate_id = schema.get("teaching_candidate_id")
                                if teaching_candidate_id:
                                    print(f"[Teaching] Using teaching_candidate_id from schema as fallback: {teaching_candidate_id}")
                                else:
                                    print(f"[Teaching] ERROR: Cannot update task status - no teaching_candidate_id available")
                                    # Continue without updating task status
                            
                            if teaching_candidate_id:
                                # Get current teaching candidates from goal
                                goal = db.get_goal_by_id(goal_id)
                                if goal and goal.get("teaching_candidate"):
                                    teaching_candidates = goal["teaching_candidate"]
                                    
                                    # Ensure it's a list
                                    if not isinstance(teaching_candidates, list):
                                        teaching_candidates = [teaching_candidates] if teaching_candidates else []
                                    
                                    print(f"[Teaching] Found {len(teaching_candidates)} teaching candidates for goal {goal_id}")
                                    print(f"[Teaching] Looking for teaching_candidate_id: {teaching_candidate_id}")
                                    
                                    # Find and mark current candidate as completed
                                    found_current = False
                                    next_available_idx = None
                                    
                                    for idx, tc in enumerate(teaching_candidates):
                                        # Compare IDs (handle both int and string types)
                                        tc_id = tc.get("id") if isinstance(tc, dict) else None
                                        if tc_id is not None:
                                            try:
                                                # Handle both int and string types for comparison
                                                if int(tc_id) == int(teaching_candidate_id):
                                                    tc["status"] = "completed"
                                                    found_current = True
                                                    print(f"[Teaching] Marked task {tc_id} ({tc.get('topic', 'unknown')}) as completed")
                                                    # Next candidate should be unlocked
                                                    if idx + 1 < len(teaching_candidates):
                                                        next_available_idx = idx + 1
                                                    break
                                            except (ValueError, TypeError) as e:
                                                print(f"[Teaching] WARNING: Could not compare IDs - tc_id={tc_id}, teaching_candidate_id={teaching_candidate_id}, error={e}")
                                                continue
                                    
                                    if not found_current:
                                        print(f"[Teaching] WARNING: Could not find teaching_candidate_id {teaching_candidate_id} in teaching_candidates list")
                                        print(f"[Teaching] Available IDs: {[tc.get('id') if isinstance(tc, dict) else 'N/A' for tc in teaching_candidates]}")
                                    
                                    # Unlock the next candidate
                                    if next_available_idx is not None:
                                        next_tc = teaching_candidates[next_available_idx]
                                        if isinstance(next_tc, dict):
                                            next_tc["status"] = "available"
                                            print(f"[Teaching] Unlocked next teaching candidate: {next_tc.get('topic', 'unknown')} (ID: {next_tc.get('id', 'unknown')})")
                                        else:
                                            print(f"[Teaching] WARNING: Next candidate at index {next_available_idx} is not a dict")
                                    else:
                                        print(f"[Teaching] No next candidate to unlock (current is last or not found)")
                                    
                                    # Save updated teaching candidates back to goal
                                    db.set_goal_teaching_candidates(goal_id, teaching_candidates)
                                    print(f"[Teaching] Saved updated teaching candidates to goal {goal_id}")
                                else:
                                    print(f"[Teaching] WARNING: Goal {goal_id} not found or has no teaching_candidate data")
                            else:
                                print(f"[Teaching] WARNING: Cannot update task status - teaching_candidate_id is None")
                    except Exception as e:
                        print(f"[Teaching] Failed to update teaching candidate status: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    await websocket.send_json({
                        "type": "teaching_complete",
                        "content": message_content,
                        "message": "You've demonstrated strong understanding of this topic!",
                        "final_markers": schema.get("understanding_markers", [])
                    })
                    _maybe_checkpoint(schema)
                else:
                    # Send message with appropriate type for UI to handle
                    response_data = {
                        "type": message_type,  # e.g., "curriculum_proposed", "assessment_question", "teaching_message"
                        "content": message_content,
                        "phase": phase,
                        "curriculum_progress": result.get("curriculum_progress", {
                            "current_step": schema.get("current_step_index", 0),
                            "total_steps": len(schema.get("curriculum_plan", {}).get("steps", [])),
                            "completed_steps": len(schema.get("curriculum_plan", {}).get("completed_step_ids", []))
                        }),
                        "narrative_summary": schema.get("narrative_summary", ""),
                    }
                    
                    # Include curriculum plan if being proposed
                    if message_type == "curriculum_proposed":
                        response_data["curriculum_plan"] = result.get("curriculum_plan")
                    
                    # Include understanding markers if in teaching phase
                    if phase == "teaching":
                        response_data["understanding_markers"] = [
                            {
                                "id": m.get("id"),
                                "name": m.get("name"),
                                "level": m.get("level"),
                                "evidence": m.get("evidence", [])[-1] if m.get("evidence") else None
                            }
                            for m in schema.get("understanding_markers", [])
                            if m.get("level") != "not_yet"
                        ]
                    
                    # Generate TTS if audio mode is enabled
                    if wants_audio and message_content and message_content.strip():
                        try:
                            import asyncio
                            loop = asyncio.get_event_loop()
                            audio_path = await asyncio.wait_for(
                                loop.run_in_executor(
                                    None,
                                    audio_service.text_to_speech,
                                    message_content
                                ),
                                timeout=5.0  # Only wait 5 seconds - fail fast
                            )
                            response_data["audio_url"] = f"/audio/{audio_path.name}"
                        except asyncio.TimeoutError:
                            print(f"[Audio] TTS generation timed out after 5s - sending response without audio")
                        except Exception as e:
                            print(f"[Audio] TTS generation failed: {e}")
                    
                    await websocket.send_json(response_data)
                    _maybe_checkpoint(schema)
                    
            except Exception as e:
                print(f"[Teaching WS] Error processing message: {e}")
                import traceback
                traceback.print_exc()
                await websocket.send_json({
                    "type": "error",
                    "message": "An error occurred. Please try again."
                })
                continue
                
    except WebSocketDisconnect:
        print(f"[Teaching WS] Disconnected: {session_id[:8]}...")
    except Exception as e:
        print(f"[Teaching WS] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except:
            pass


class TeachingChatRequest(BaseModel):
    """Legacy teaching chat request - kept for backwards compatibility."""
    session_id: str
    message: str

class TeachingChatResponse(BaseModel):
    response: str
    curriculum_progress: Optional[dict] = None
    narrative_summary: Optional[str] = None

@app.post("/api/teaching/chat", response_model=TeachingChatResponse)
async def teaching_chat(request: TeachingChatRequest):
    """
    Process a message in a teaching session via REST (alternative to WebSocket).
    Primarily for backwards compatibility - WebSocket is preferred.
    """
    try:
        orchestrator = teaching_sessions.get(request.session_id)
        
        if not orchestrator:
            raise HTTPException(status_code=404, detail="Teaching session not found. Use /api/teaching/start first.")
        
        # Process message
        response = orchestrator.process_user_message(request.message)
        
        # Get current state
        schema = orchestrator.get_schema()
        
        return TeachingChatResponse(
            response=response,
            curriculum_progress={
                "current_step": schema.get("current_step_index", 0),
                "total_steps": len(schema.get("curriculum_plan", {}).get("steps", [])),
                "completed_steps": len(schema.get("curriculum_plan", {}).get("completed_step_ids", []))
            },
            narrative_summary=schema.get("narrative_summary")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Teaching Chat] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/discovery/start", response_model=SessionCreateResponse)
async def start_discovery(request: SessionCreateRequest = SessionCreateRequest()):
    """Create a new discovery session or resume an existing one."""
    try:
        conversation_history = []
        schema_state = None
        profile_summary = None
        is_resumed = False
        
        # Check if resuming a goal session
        if request.goal_id and request.user_id:
            existing = db.get_session_for_goal(request.goal_id)
            if existing and existing.get("session_id"):
                # Resume existing goal session
                session_id = existing["session_id"]
                conversation_history = existing.get("conversation_history", [])
                schema_state = existing.get("schema_state")
                profile_summary = existing.get("profile_summary")
                is_resumed = True
                print(f"[Discovery] Resuming goal session: {session_id[:8]}... ({len(conversation_history)} messages)")
        
        # Check if resuming exploration session
        elif request.user_id and not request.goal:
            exploration = db.get_or_create_exploration_session(request.user_id)
            if not exploration.get("is_new"):
                session_id = exploration["session_id"]
                conversation_history = exploration.get("conversation_history", [])
                schema_state = exploration.get("schema_state")
                profile_summary = exploration.get("profile_summary")
                is_resumed = True
                print(f"[Discovery] Resuming exploration session: {session_id[:8]}... ({len(conversation_history)} messages)")
        
        # Generate new session if not resuming
        if not is_resumed:
            session_id = str(uuid.uuid4())
            print(f"[Discovery] Creating new session: {session_id[:8]}...")
            
            # If this is for a goal, create session with goal_id
            exploration_history = None
            if request.goal_id and request.user_id:
                db.create_session_with_type(session_id, request.user_id, 'goal', request.goal_id)
                # Get exploration conversation history to provide context for goal chat
                exploration = db.get_user_exploration_session(request.user_id)
                if exploration and exploration.get("conversation_history"):
                    # Include exploration history as context (last 10 messages to avoid token bloat)
                    exploration_history = exploration.get("conversation_history", [])
                    exploration_history = exploration_history[-10:] if len(exploration_history) > 10 else exploration_history
                    print(f"[Discovery] Including {len(exploration_history)} messages from exploration chat for goal context")
            elif request.user_id:
                db.create_session_with_type(session_id, request.user_id, 'exploration')

        # Create/resume session in memory
        session_data = await session_manager.create_session(
            session_id,
            debug=False,
            model_config=request.models,
            user_goal=request.goal,
            user_id=request.user_id,
            conversation_history=conversation_history if is_resumed else None,
            schema_state=schema_state if is_resumed else None,
            exploration_history=exploration_history if not is_resumed and request.goal_id else None
        )

        # Get opening question for new sessions OR resumed sessions with no history
        # (resumed with no history happens when goal panel is opened for first time)
        opening_message = ""
        audio_url = None
        needs_opening = not is_resumed or len(conversation_history) == 0
        if needs_opening:
            opening_message = session_data.discovery_session.start()
            # Skip TTS for opening message - only generate if user explicitly enables audio mode
            audio_url = None

        return SessionCreateResponse(
            session_id=session_id,
            opening_message=opening_message,
            audio_url=audio_url,
            conversation_history=conversation_history,
            is_resumed=is_resumed,
            profile_summary=profile_summary
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/discovery/{session_id}")
async def discovery_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for discovery phase conversation with streaming support."""
    await websocket.accept()

    # Get or create session
    session_data = await session_manager.get_session(session_id)
    if not session_data:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    # Cache DB session info for checkpoint attribution (best-effort)
    try:
        session_info = db.get_session_by_id(session_id) or {}
    except Exception:
        session_info = {}

    def _maybe_checkpoint():
        """Persist a sparse trajectory checkpoint for this user (best-effort)."""
        print(f"[Trajectory] _maybe_checkpoint called for session {session_id[:8]}...")
        try:
            discovery = session_data.discovery_session
            if not discovery:
                print(f"[Trajectory] No discovery session found, skipping checkpoint")
                return
            schema_snapshot = discovery.get_schema()
            turns = (schema_snapshot.get("interview_state", {}) or {}).get("turns_elapsed")
            user_id_val = getattr(discovery, "user_id", None) or session_info.get("user_id")
            print(f"[Trajectory] Calling checkpoint writer for user {user_id_val[:8] if user_id_val else 'None'}... at turn {turns}")
            checkpoint_id = db.maybe_write_trajectory_checkpoint(
                user_id=user_id_val,
                session_id=session_id,
                session_type=session_info.get("session_type") or "exploration",
                goal_id=session_info.get("goal_id"),
                teaching_candidate_id=session_info.get("teaching_candidate_id"),
                schema_state=schema_snapshot,
                conversation_history=getattr(discovery, "conversation_history", None),
                turn_index=turns,
            )
            if checkpoint_id:
                print(f"[Trajectory] ✅ Checkpoint {checkpoint_id} written at turn {turns}")
            else:
                print(f"[Trajectory] No checkpoint needed (turn {turns}, cadence or event condition not met)")
        except Exception as e:
            print(f"[Trajectory] Discovery checkpoint failed: {e}")
            import traceback
            traceback.print_exc()

    try:
        while True:
            # Receive message from frontend
            print(f"[WebSocket] Waiting for message on session {session_id[:8]}...")
            data = await websocket.receive_json()
            print(f"[WebSocket] Received data: {data}")
            user_message = data.get("content", "")

            if not user_message:
                continue

            # Check if we should be proposing a curriculum (better UX feedback)
            should_propose_curriculum = False
            try:
                schema = session_data.discovery_session.schema
                assessment_conf = schema.prior_knowledge_assessment.confidence
                turns = schema.interview_state.turns_elapsed + 1
                has_candidates = len(schema.teaching_candidates) > 0
                already_proposed = schema.task_curriculum.proposed

                should_propose_curriculum = (
                    not already_proposed and
                    has_candidates and
                    (assessment_conf >= 0.5 or turns >= 8)
                )
            except:
                pass  # If anything goes wrong, just use default status

            # Send status: analyzing or proposing
            status_message = "Proposing curriculum..." if should_propose_curriculum else "Analyzing your response..."
            await websocket.send_json({
                "type": "status",
                "status": status_message
            })

            # Wrap all command processing in try-except for safety
            try:
                # Skip voice detection for explicit commands (they start with __)
                is_explicit_command = user_message.startswith("__") and user_message.endswith("__")
                
                if not is_explicit_command:
                    # Voice command detection for goal/teaching accept/reject (only for natural language)
                    lower_msg = user_message.lower().strip()
                    
                    # Check if there's a pending goal proposal
                    has_pending_goal = session_data.discovery_session.schema.interview_state.proposed_goal is not None
                    
                    # Check if there's a pending task curriculum proposal
                    has_pending_curriculum = (
                        session_data.discovery_session.schema.task_curriculum.proposed and
                        not session_data.discovery_session.schema.task_curriculum.accepted and
                        len(session_data.discovery_session.schema.task_curriculum.tasks) > 0
                    )
                    
                    # Check if there's a pending single teaching candidate (legacy)
                    # Note: proposed_teaching_ids may not exist in all schema versions
                    has_pending_teaching = False
                    try:
                        interview_state = session_data.discovery_session.schema.interview_state
                        if hasattr(interview_state, 'proposed_teaching_ids') and interview_state.proposed_teaching_ids:
                            has_pending_teaching = (
                                len(interview_state.proposed_teaching_ids) > 0 and
                                (not hasattr(interview_state, 'batch_proposal_pending') or interview_state.batch_proposal_pending == False)
                            )
                    except (AttributeError, TypeError):
                        has_pending_teaching = False
                    
                    # Detect voice commands for acceptance
                    accept_phrases = ['yes', 'yeah', 'yep', 'sounds good', 'sounds great', 'accept', 'let\'s do it', 
                                     'perfect', 'that works', 'i like it', 'go for it', 'absolutely', 'sure', 'ok', 'okay', 'i accept']
                    reject_phrases = ['no', 'nope', 'not quite', 'not really', 'something else', 'different', 
                                     'reject', 'pass', 'skip', 'change', 'try again']
                    
                    is_accept = any(phrase in lower_msg for phrase in accept_phrases) and len(lower_msg) < 50
                    is_reject = any(phrase in lower_msg for phrase in reject_phrases) and len(lower_msg) < 50
                    
                    # Convert voice accept/reject to commands
                    if has_pending_goal and is_accept:
                        print(f"[Voice] Detected goal acceptance: '{user_message}'")
                        user_message = "__ACCEPT_GOAL__"
                    elif has_pending_goal and is_reject:
                        print(f"[Voice] Detected goal rejection: '{user_message}'")
                        user_message = "__REJECT_GOAL__"
                    elif has_pending_curriculum and is_accept:
                        print(f"[Voice] Detected curriculum acceptance: '{user_message}'")
                        user_message = "__ACCEPT_CURRICULUM__"
                    elif has_pending_curriculum and is_reject:
                        print(f"[Voice] Detected curriculum rejection: '{user_message}'")
                        user_message = "__REJECT_CURRICULUM__"
                    elif has_pending_teaching and is_accept:
                        print(f"[Voice] Detected teaching acceptance: '{user_message}'")
                        user_message = "__ACCEPT_TEACHING__"
                    elif has_pending_teaching and is_reject:
                        print(f"[Voice] Detected teaching rejection: '{user_message}'")
                        user_message = "__REJECT_TEACHING__"
                
                # Check for onboarding command (should not be displayed in chat)
                is_onboarding_message = False
                if user_message.startswith("__ONBOARDING__"):
                    # Extract the actual background info
                    background_info = user_message.replace("__ONBOARDING__", "", 1)
                    # Process it but don't add to visible conversation history
                    # The orchestrator will use it for context but we'll mark it as hidden
                    user_message = background_info
                    is_onboarding_message = True
                    print(f"[WebSocket] Onboarding message detected - will use for context but not add to visible history")
                
                # Check for special commands (goal accept/reject)
                if user_message == "__ACCEPT_GOAL__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    result = session_data.discovery_session.accept_proposed_goal()

                    # Check for error
                    if "error" in result:
                        await websocket.send_json({
                            "type": "error",
                            "message": result["error"]
                        })
                        continue

                    # Check for error
                    if "error" in result or not result.get("success"):
                        await websocket.send_json({
                            "type": "error",
                            "message": result.get("error") or result.get("message", "Failed to accept goal")
                        })
                        continue

                    # Send data for frontend to create new goal panel
                    await websocket.send_json({
                        "type": "create_goal_panel",
                        "goal": result.get("goal", ""),
                        "goal_id": result.get("goal_id", 0),
                        "message": result.get("message", "Goal accepted")
                    })
                    _maybe_checkpoint()
                    continue

                if user_message == "__REJECT_GOAL__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    import asyncio
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        session_data.discovery_session.reject_proposed_goal
                    )
                    await websocket.send_json({
                        "type": "message",
                        "content": response,
                        "audio_url": None
                    })
                    _maybe_checkpoint()
                    continue

                # Check for teaching candidate accept/reject commands
                if user_message == "__ACCEPT_TEACHING__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    result = session_data.discovery_session.accept_proposed_teaching()

                    # Check for error
                    if not result.get("success"):
                        await websocket.send_json({
                            "type": "error",
                            "message": result.get("message", "Failed to accept teaching candidate")
                        })
                        continue

                    # Save teaching candidate to the goal in database
                    try:
                        session_info = db.get_session_by_id(session_id)
                        if session_info and session_info.get("goal_id"):
                            db.update_goal_teaching_candidate(
                                session_info["goal_id"],
                                result.get("candidate", {})
                            )
                            print(f"[Teaching] Saved teaching candidate to goal {session_info['goal_id']}")
                    except Exception as e:
                        print(f"[Teaching] Failed to save teaching candidate to DB: {e}")

                    # Send data for frontend to create new teaching panel
                    await websocket.send_json({
                        "type": "create_teaching_panel",
                        "candidate": result.get("candidate", {}),
                        "message": result.get("message", "Teaching candidate accepted")
                    })
                    _maybe_checkpoint()
                    continue

                if user_message == "__REJECT_TEACHING__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    import asyncio
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        session_data.discovery_session.reject_proposed_teaching
                    )
                    await websocket.send_json({
                        "type": "message",
                        "content": response,
                        "audio_url": None
                    })
                    _maybe_checkpoint()
                    continue

                # Check for manual learning path generation command
                if user_message == "__GENERATE_LEARNING_PATH__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    result = session_data.discovery_session.generate_learning_path()

                    if not result.get("success"):
                        await websocket.send_json({
                            "type": "error",
                            "message": result.get("message", "Failed to generate learning path")
                        })
                        continue

                    # Check if curriculum was generated and proposed
                    if session_data.discovery_session.schema.task_curriculum.proposed:
                        tasks = session_data.discovery_session.schema.task_curriculum.tasks
                        curriculum_message = result.get("message", "Learning path generated")
                        
                        # Send a simple message - the UI component will show the full curriculum
                        simple_message = f"I've designed a learning path with {len(tasks)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."
                        
                        await websocket.send_json({
                            "type": "task_curriculum_proposed",
                            "content": simple_message,
                            "curriculum": {
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
                            },
                            "tasks": [
                                {
                                    "id": task.id,
                                    "topic": task.topic,
                                    "justification": task.justification,
                                    "prerequisites": task.prerequisites,
                                    "status": task.status
                                }
                                for task in tasks
                            ],
                            "message": simple_message
                        })
                    else:
                        # Fallback: send the message even if curriculum wasn't fully processed
                        await websocket.send_json({
                            "type": "message",
                            "content": result.get("message", "Learning path generation in progress"),
                            "role": "assistant"
                        })
                    
                    _maybe_checkpoint()
                    continue

                # Check for curriculum accept command (batch task proposal)
                if user_message == "__ACCEPT_CURRICULUM__":
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    result = session_data.discovery_session.accept_proposed_curriculum()

                    if not result.get("success"):
                        await websocket.send_json({
                            "type": "error",
                            "message": result.get("message", "Failed to accept curriculum")
                        })
                        continue

                    # Save all tasks to the goal in database as an array
                    try:
                        session_info = db.get_session_by_id(session_id)
                        goal_id = None
                        
                        # Try to get goal_id from session
                        if session_info and session_info.get("goal_id"):
                            goal_id = session_info["goal_id"]
                        # Fallback: find goal by user_id and goal_text from schema
                        elif session_info and session_data.discovery_session.schema.interview_state.user_goal:
                            user_id = session_info.get("user_id")
                            goal_text = session_data.discovery_session.schema.interview_state.user_goal
                            if user_id:
                                # Find the most recent goal matching this text
                                goals = db.get_user_goals(user_id)
                                matching_goal = next((g for g in goals if g["goal_text"] == goal_text), None)
                                if matching_goal:
                                    goal_id = matching_goal["id"]
                                    print(f"[Curriculum] Found goal by text: {goal_id}")
                        
                        if goal_id:
                            tasks = result.get("tasks", [])
                            # Save entire task list as teaching candidates array
                            db.set_goal_teaching_candidates(goal_id, tasks)
                            print(f"[Curriculum] Saved {len(tasks)} tasks to goal {goal_id}")
                        else:
                            print(f"[Curriculum] WARNING: Could not find goal_id to save tasks. Session: {session_info}, Goal: {session_data.discovery_session.schema.interview_state.user_goal if session_data.discovery_session else 'N/A'}")
                    except Exception as e:
                        print(f"[Curriculum] Failed to save tasks to DB: {e}")
                        import traceback
                        traceback.print_exc()

                    # Send data for frontend - first task is available, others locked
                    tasks = result.get("tasks", [])
                    first_task = tasks[0] if tasks else None
                    
                    await websocket.send_json({
                        "type": "task_curriculum_accepted",
                        "tasks": tasks,
                        "first_task": first_task,
                        "content": f"Great! Let's start with: **{first_task['topic']}**" if first_task else "Curriculum accepted!",
                        "message": result.get("message", "Curriculum accepted")
                    })
                    _maybe_checkpoint()
                    continue

                # Process message in thread pool to avoid blocking the event loop
                # (blocking calls can cause WebSocket timeouts)
                import asyncio
                loop = asyncio.get_event_loop()
                # Create a wrapper function to pass the skip_history parameter
                def process_with_flag():
                    return session_data.discovery_session.process_user_message(
                        user_message, 
                        skip_history=is_onboarding_message
                    )
                response = await loop.run_in_executor(
                    None,  # Use default thread pool
                    process_with_flag
                )

                # If response is empty (onboarding with existing opening), skip sending anything
                if not response or response.strip() == "":
                    # Clear any status and return early
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    _maybe_checkpoint()
                    continue

                # Check if a goal was proposed (needs user confirmation)
                if response.startswith("__GOAL_PROPOSED__:"):
                    proposed_goal = response.split(":", 1)[1]
                    goal_message = f"I think I've identified a learning goal for you: {proposed_goal}. Does this sound right?"
                    
                    # Skip TTS for goal proposal - only generate if audio mode enabled
                    goal_audio_url = None
                    
                    # Clear status before sending goal proposal
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    await websocket.send_json({
                        "type": "goal_proposed",
                        "goal": proposed_goal,
                        "content": goal_message,
                        "audio_url": goal_audio_url,
                        "message": f"**Goal identified:** {proposed_goal}"
                    })
                    _maybe_checkpoint()
                    continue

                # Check if a task curriculum was proposed (needs user confirmation)
                if response.startswith("__TASK_CURRICULUM_PROPOSED__:"):
                    import json as json_module
                    curriculum_json = response.split(":", 1)[1]
                    curriculum = json_module.loads(curriculum_json)
                    
                    # Build a message showing the proposed learning path
                    tasks = curriculum.get('tasks', [])
                    print(f"[Backend] Curriculum proposal: {len(tasks)} tasks found")
                    overall_justification = curriculum.get('overall_justification', "Here's the learning path I've designed for you:")
                    
                    # Format task list with better error handling
                    if tasks and len(tasks) > 0:
                        task_list = "\n\n".join([
                            f"**{i+1}. {t.get('topic', 'Task')}**\n{t.get('justification', 'Explore this topic')}" 
                            for i, t in enumerate(tasks)
                        ])
                        curriculum_message = f"{overall_justification}\n\n{task_list}\n\n---\n\nThis is my best guess at the complete journey. We can adjust this as we learn more about what works for you."
                    else:
                        print(f"[Backend] WARNING: No tasks found in curriculum! Curriculum keys: {curriculum.keys()}")
                        curriculum_message = f"{overall_justification}\n\n*No tasks were generated. Please try generating the learning path again.*"
                    
                    # Generate TTS for curriculum proposal (non-blocking with timeout)
                    curriculum_audio_url = None
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        short_message = f"I've designed a learning path with {len(tasks)} topics. The first is {tasks[0]['topic'] if tasks else 'available'} to start."
                        audio_path = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                audio_service.text_to_speech,
                                short_message
                            ),
                            timeout=30.0  # 30 second timeout
                        )
                        curriculum_audio_url = f"/audio/{audio_path.name}"
                    except asyncio.TimeoutError:
                        print(f"[Audio] TTS for curriculum proposal timed out after 30s")
                    except Exception as e:
                        print(f"[Audio] TTS for curriculum proposal failed: {e}")
                    
                    # Clear status before sending curriculum proposal
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    # Send a simple message - the UI component will show the full curriculum
                    simple_message = f"I've designed a learning path with {len(tasks)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."
                    await websocket.send_json({
                        "type": "task_curriculum_proposed",
                        "curriculum": curriculum,
                        "content": simple_message,
                        "audio_url": curriculum_audio_url,
                        "message": simple_message
                    })
                    _maybe_checkpoint()
                    continue

                # Check if a teaching candidate was proposed (needs user confirmation) - legacy single candidate
                if response.startswith("__TEACHING_PROPOSED__:"):
                    import json as json_module
                    candidate_json = response.split(":", 1)[1]
                    candidate = json_module.loads(candidate_json)
                    teaching_message = f"I think I found a great starting point: {candidate['topic']}. Want to explore this?"
                    
                    # Generate TTS for teaching proposal (non-blocking with timeout)
                    teaching_audio_url = None
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        audio_path = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                audio_service.text_to_speech,
                                teaching_message
                            ),
                            timeout=30.0  # 30 second timeout
                        )
                        teaching_audio_url = f"/audio/{audio_path.name}"
                    except asyncio.TimeoutError:
                        print(f"[Audio] TTS for teaching proposal timed out after 30s")
                    except Exception as e:
                        print(f"[Audio] TTS for teaching proposal failed: {e}")
                    
                    # Clear status before sending teaching proposal
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    await websocket.send_json({
                        "type": "teaching_proposed",
                        "candidate": candidate,
                        "content": teaching_message,
                        "audio_url": teaching_audio_url,
                        "message": f"I think I found a great starting point: **{candidate['topic']}**"
                    })
                    _maybe_checkpoint()
                    continue

                # Skip TTS by default - only generate if user explicitly enables audio mode
                # This prevents hanging on slow ElevenLabs API calls
                audio_url = None
                wants_audio = data.get("audio_mode", False) or data.get("audio", False)
                
                if wants_audio and response and response.strip():  # Only generate if explicitly requested
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        # Very short timeout - if TTS takes more than 5 seconds, skip it
                        audio_path = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                audio_service.text_to_speech,
                                response
                            ),
                            timeout=5.0  # Only wait 5 seconds - fail fast
                        )
                        audio_url = f"/audio/{audio_path.name}"
                    except asyncio.TimeoutError:
                        print(f"[Audio] TTS generation timed out after 5s - sending response without audio")
                        audio_url = None
                    except Exception as e:
                        print(f"[Audio] TTS generation failed: {e}")
                        audio_url = None
                # If audio_mode not enabled, skip TTS entirely (no logging needed)

                # Check if discovery is complete
                if session_data.discovery_session.is_complete():
                    # Clear status
                    await websocket.send_json({
                        "type": "status",
                        "status": ""
                    })
                    final_topic = session_data.discovery_session.get_final_topic()

                    # Validate final_topic before using it
                    if not final_topic or not hasattr(final_topic, 'topic'):
                        print(f"[WS ERROR] Invalid final_topic returned from get_final_topic()")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to extract topic information"
                        })
                        continue

                    await session_manager.save_final_topic(session_id, final_topic)

                    # Send topic found message
                    await websocket.send_json({
                        "type": "topic_found",
                        "content": response,
                        "audio_url": audio_url,
                        "topic": {
                            "topic": final_topic.topic,
                            "user_confusion": final_topic.user_confusion,
                            "stakes": final_topic.stakes,
                            "learning_hook": final_topic.learning_hook,
                            "suggested_angles": final_topic.suggested_angles,
                            "scores": final_topic.scores.to_dict() if final_topic.scores else {}
                        }
                    })
                    _maybe_checkpoint()
                else:
                    # Clear status before sending message
                    await websocket.send_json({
                        "type": "status",
                        "status": ""  # Empty status clears it
                    })
                    # Send regular message
                    await websocket.send_json({
                        "type": "message",
                        "content": response,
                        "audio_url": audio_url
                    })
                    _maybe_checkpoint()

            except Exception as e:
                # Command processing failed - send error but don't disconnect
                print(f"[WS ERROR] Command processing failed: {e}")
                import traceback
                traceback.print_exc()
                await websocket.send_json({
                    "type": "error",
                    "message": f"An error occurred processing your message. Please try again."
                })
                # Continue to next message instead of disconnecting
                continue

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"Error in discovery websocket: {e}")
        import traceback
        traceback.print_exc()

        # Check if it's a rate limit error
        error_message = str(e)
        if "rate limit" in error_message.lower() or "429" in error_message or "token" in error_message.lower() and "limit" in error_message.lower():
            friendly_message = "⚠️ API rate limit reached. The service has hit its daily token quota. Please try again later or contact support."
        else:
            friendly_message = f"An error occurred: {error_message}"

        try:
            await websocket.send_json({"type": "error", "message": friendly_message})
        except Exception as e:
            print(f"[WebSocket] Error sending error message: {e}")

        try:
            await websocket.close()
        except Exception as e:
            print(f"[WebSocket] Error closing connection: {e}")


@app.get("/api/discovery/{session_id}/schema")
async def get_discovery_schema(session_id: str):
    """Get current discovery schema for debugging."""
    session_data = await session_manager.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get schema from discovery session
    schema = session_data.discovery_session.get_schema()
    return schema


# ============================================
# Panel Endpoints (Context, Draft, Terminal Tabs)
# ============================================

from backend.services.terminal_manager import terminal_manager
from backend.services.terminal_observer import create_terminal_observer
from backend.services.document_suggestion import document_suggestion_service
from backend.services.suggestion_router import create_suggestion_router

# Initialize suggestion router with database
suggestion_router = create_suggestion_router(db)

# Pydantic models for panel endpoints
class ContextTextRequest(BaseModel):
    goal_id: int
    user_id: str
    text_content: str
    content_type: str = "text"

class ContextResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    content_type: str
    text_content: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    token_count: int
    is_active: bool
    created_at: Optional[str] = None

class DocumentCreateRequest(BaseModel):
    goal_id: int
    user_id: str
    title: str = "Untitled"
    document_type: str = "notes"
    content: Optional[dict] = None
    plain_text: Optional[str] = None

class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    document_type: Optional[str] = None
    content: Optional[dict] = None
    plain_text: Optional[str] = None

class DocumentConfigRequest(BaseModel):
    formatting: bool = True
    content: bool = True
    tasks: bool = False

class DocumentResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    title: str
    document_type: str
    content: Optional[dict] = None
    plain_text: Optional[str] = None
    suggestion_config: dict
    version: int
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class TerminalStartRequest(BaseModel):
    goal_id: int
    user_id: str
    working_directory: str = "~"

class TerminalResponse(BaseModel):
    id: int
    session_id: str
    goal_id: int
    user_id: str
    working_directory: str
    is_active: bool
    created_at: Optional[str] = None

class ChannelCreateRequest(BaseModel):
    goal_id: int
    user_id: str
    channel_type: str = "custom"
    name: str
    suggestion_context: Optional[dict] = None
    source_binding: Optional[str] = None

class ChannelContextRequest(BaseModel):
    instructions: Optional[str] = None
    focus_areas: Optional[List[str]] = None
    excluded_topics: Optional[List[str]] = None

class ChannelResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    channel_type: str
    name: str
    suggestion_context: dict
    source_binding: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None

class ChannelMessageResponse(BaseModel):
    id: int
    channel_id: int
    role: str
    content: str
    message_type: str
    source: Optional[str] = None
    metadata: dict
    created_at: Optional[str] = None


# ---- Context Tab Endpoints ----

@app.post("/api/goal/{goal_id}/context", response_model=ContextResponse)
async def add_context(goal_id: int, request: ContextTextRequest):
    """Add text context to a goal."""
    try:
        # Verify goal_id matches
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        context = db.create_goal_context(
            goal_id=request.goal_id,
            user_id=request.user_id,
            content_type=request.content_type,
            text_content=request.text_content,
            processed_content=request.text_content,  # For text, processed = original
            token_count=len(request.text_content.split())  # Rough estimate
        )
        return ContextResponse(**context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goal/{goal_id}/contexts", response_model=List[ContextResponse])
async def get_contexts(goal_id: int):
    """Get all context items for a goal."""
    try:
        contexts = db.get_goal_contexts(goal_id)
        return [ContextResponse(**c) for c in contexts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/goal/{goal_id}/context/{context_id}", response_model=ContextResponse)
async def update_context(goal_id: int, context_id: int, updates: dict):
    """Update a context item."""
    try:
        context = db.update_goal_context(context_id, updates)
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")
        return ContextResponse(**context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/goal/{goal_id}/context/{context_id}")
async def delete_context(goal_id: int, context_id: int):
    """Delete a context item (soft delete)."""
    try:
        success = db.delete_goal_context(context_id, soft_delete=True)
        if not success:
            raise HTTPException(status_code=404, detail="Context not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Draft Tab Endpoints ----

@app.post("/api/goal/{goal_id}/document", response_model=DocumentResponse)
async def create_document(goal_id: int, request: DocumentCreateRequest):
    """Create a new document for a goal."""
    try:
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        document = db.create_goal_document(
            goal_id=request.goal_id,
            user_id=request.user_id,
            title=request.title,
            document_type=request.document_type,
            content=request.content,
            plain_text=request.plain_text
        )
        return DocumentResponse(**document)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goal/{goal_id}/documents", response_model=List[DocumentResponse])
async def get_documents(goal_id: int):
    """Get all documents for a goal."""
    try:
        documents = db.get_goal_documents(goal_id)
        return [DocumentResponse(**d) for d in documents]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/document/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int):
    """Get a specific document."""
    try:
        document = db.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/document/{document_id}", response_model=DocumentResponse)
async def update_document(document_id: int, request: DocumentUpdateRequest):
    """Update a document."""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        document = db.update_document(document_id, updates)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/document/{document_id}/config", response_model=DocumentResponse)
async def update_document_config(document_id: int, request: DocumentConfigRequest):
    """Update document suggestion preferences."""
    try:
        config = request.model_dump()
        document = db.update_document_suggestion_config(document_id, config)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/document/{document_id}/expand-suggestion")
async def expand_suggestion(document_id: int, request: dict):
    """Expand a document suggestion with implementation ideas and questions."""
    try:
        suggestion = request.get("suggestion", {})
        document_content = request.get("document_content", "")
        goal_id = request.get("goal_id")
        
        if not suggestion or not suggestion.get("text"):
            raise HTTPException(status_code=400, detail="Suggestion text required")
        
        # Get goal context
        goal = db.get_goal_by_id(goal_id) if goal_id else None
        goal_text = goal["goal_text"] if goal else ""
        
        # Use LLM to expand the suggestion
        from src.llm_client import LLMClient
        from src.config import get_model_name
        
        llm = LLMClient()
        model = get_model_name("ranker", default="openai:gpt-4o-mini")
        
        prompt = f"""You are helping someone improve their document. They received this suggestion:

SUGGESTION TYPE: {suggestion.get('suggestion_type', 'general')}
SUGGESTION: {suggestion.get('text', '')}
LOCATION: {suggestion.get('location', 'N/A')}

CONTEXT:
- Goal: "{goal_text}"
- Document content (excerpt): {document_content[:1000]}

Generate a concise, direct message that includes:
1. Brief explanation of the suggestion (1-2 sentences)
2. 2-3 specific, actionable implementation ideas
3. 1-2 focused questions to guide implementation

Write directly and concisely. Skip greetings and filler phrases like "Hey there!" or "I noticed". Get straight to the point. Return just the message text, no JSON or formatting markers."""

        expanded_message = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.7,
            max_tokens=500
        )
        
        return {
            "expanded_message": expanded_message.strip(),
            "suggestion": suggestion
        }
    except Exception as e:
        print(f"[ExpandSuggestion] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ---- Terminal Tab Endpoints ----

@app.post("/api/terminal/start", response_model=TerminalResponse)
async def start_terminal(request: TerminalStartRequest):
    """Initialize a terminal session."""
    try:
        session_id = str(uuid.uuid4())

        # Create terminal session in database
        terminal = db.create_terminal_session(
            session_id=session_id,
            goal_id=request.goal_id,
            user_id=request.user_id,
            working_directory=request.working_directory
        )

        # Create actual PTY session
        await terminal_manager.create_session(
            session_id=session_id,
            working_dir=request.working_directory
        )

        return TerminalResponse(**terminal)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/terminal/{session_id}/history")
async def get_terminal_history(session_id: str, limit: int = 50):
    """Get command history for a terminal session."""
    try:
        history = db.get_terminal_history(session_id, limit=limit)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Chat Channel Endpoints ----

@app.post("/api/goal/{goal_id}/channel", response_model=ChannelResponse)
async def create_channel(goal_id: int, request: ChannelCreateRequest):
    """Create a new chat channel for a goal."""
    try:
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        channel = db.create_chat_channel(
            goal_id=request.goal_id,
            user_id=request.user_id,
            channel_type=request.channel_type,
            name=request.name,
            suggestion_context=request.suggestion_context or {},
            source_binding=request.source_binding
        )
        return ChannelResponse(**channel)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goal/{goal_id}/channels", response_model=List[ChannelResponse])
async def get_channels(goal_id: int):
    """Get all chat channels for a goal."""
    try:
        channels = db.get_goal_channels(goal_id)
        return [ChannelResponse(**c) for c in channels]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/channel/{channel_id}/context", response_model=ChannelResponse)
async def update_channel_context(channel_id: int, request: ChannelContextRequest):
    """Update suggestion context for a channel."""
    try:
        context = {
            "instructions": request.instructions,
            "focus_areas": request.focus_areas or [],
            "excluded_topics": request.excluded_topics or []
        }
        channel = db.update_channel_suggestion_context(channel_id, context)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return ChannelResponse(**channel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/channel/{channel_id}/messages", response_model=List[ChannelMessageResponse])
async def get_channel_messages(channel_id: int, limit: int = 100, offset: int = 0):
    """Get messages for a channel."""
    try:
        messages = db.get_channel_messages(channel_id, limit=limit, offset=offset)
        return [ChannelMessageResponse(**m) for m in messages]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/goal/{goal_id}/panels/init")
async def initialize_goal_panels(goal_id: int, user_id: str = Query(None)):
    """Initialize default chat channels for a goal's panel system."""
    try:
        # Get user_id from query param or from goal
        if not user_id:
            goal = db.get_goal_by_id(goal_id)
            if goal:
                user_id = goal.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        result = db.initialize_goal_panels(goal_id, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Panel WebSocket Handlers
# ============================================

# Store active WebSocket connections
active_document_connections: dict = {}  # document_id -> List[WebSocket]
active_terminal_connections: dict = {}  # session_id -> List[WebSocket]
active_channel_connections: dict = {}  # channel_id -> List[WebSocket]
terminal_observers: dict = {}  # session_id -> TerminalObserver


@app.websocket("/ws/document/{document_id}")
async def document_websocket(websocket: WebSocket, document_id: int):
    """WebSocket for real-time document sync and AI suggestions."""
    await websocket.accept()

    # Add to connections
    if document_id not in active_document_connections:
        active_document_connections[document_id] = []
    active_document_connections[document_id].append(websocket)

    try:
        # Get document info
        document = db.get_document_by_id(document_id)
        if not document:
            await websocket.send_json({"type": "error", "message": "Document not found"})
            await websocket.close()
            return

        goal_id = document["goal_id"]

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "update":
                # Client sends document update
                content = data.get("content", {})
                plain_text = data.get("plain_text", "")

                # Only update if we have actual content (avoid empty updates)
                updates = {}
                if plain_text is not None and plain_text != "":
                    updates["plain_text"] = plain_text
                if content is not None and content != {}:
                    updates["content"] = content
                
                # Only update database if there are actual changes
                updated = None
                if updates:
                    updated = db.update_document(document_id, updates)

                # Send sync acknowledgment
                await websocket.send_json({
                    "type": "sync_ack",
                    "version": updated["version"] if updated else 0
                })

                # Schedule AI suggestions with debouncing
                async def send_suggestions(suggestions):
                    try:
                        # Properly serialize dataclass to dict
                        from dataclasses import asdict
                        suggestions_dict = [asdict(s) for s in suggestions]
                        await websocket.send_json({
                            "type": "suggestions",
                            "suggestions": suggestions_dict
                        })

                        # Also route to appropriate channels
                        await suggestion_router.route_document_suggestions(
                            goal_id=goal_id,
                            document_id=document_id,
                            suggestions=suggestions_dict
                        )
                    except Exception as e:
                        print(f"[DocumentWS] Error sending suggestions: {e}")

                # Get goal context for suggestions
                goal = db.get_goal_by_id(goal_id)
                goal_context = {"goal_text": goal["goal_text"]} if goal else {}
                config = document.get("suggestion_config", {})

                from backend.services.document_suggestion import SuggestionConfig as DocSuggestionConfig
                suggestion_config = DocSuggestionConfig(
                    formatting=config.get("formatting", True),
                    content=config.get("content", True),
                    tasks=config.get("tasks", False)
                )

                document_suggestion_service.schedule_suggestions(
                    document_id=document_id,
                    plain_text=plain_text,
                    goal_context=goal_context,
                    config=suggestion_config,
                    callback=send_suggestions
                )

            elif msg_type == "request_suggestion":
                # Client explicitly requests suggestion
                print(f"[DocumentWS] Requesting suggestions for document {document_id}")
                selection = data.get("selection", "")
                plain_text = selection or document.get("plain_text", "")
                
                print(f"[DocumentWS] Document plain_text length: {len(plain_text) if plain_text else 0}")
                
                if not plain_text or len(plain_text.strip()) < 20:
                    error_msg = "Document needs at least 20 characters for AI analysis"
                    print(f"[DocumentWS] {error_msg}")
                    await websocket.send_json({
                        "type": "error",
                        "message": error_msg
                    })
                    return

                goal = db.get_goal_by_id(goal_id)
                goal_context = {"goal_text": goal["goal_text"]} if goal else {}
                config = document.get("suggestion_config", {})

                from backend.services.document_suggestion import SuggestionConfig as DocSuggestionConfig
                suggestion_config = DocSuggestionConfig(
                    formatting=config.get("formatting", True),
                    content=config.get("content", True),
                    tasks=config.get("tasks", False)
                )

                try:
                    print(f"[DocumentWS] Generating suggestions for {len(plain_text)} characters...")
                    print(f"[DocumentWS] Goal context: {goal_context}")
                    print(f"[DocumentWS] Suggestion config: formatting={suggestion_config.formatting}, content={suggestion_config.content}, tasks={suggestion_config.tasks}")
                    
                    suggestions = await document_suggestion_service.generate_suggestions(
                        document_id=document_id,
                        plain_text=plain_text,
                        goal_context=goal_context,
                        config=suggestion_config
                    )
                    
                    print(f"[DocumentWS] Generated {len(suggestions)} suggestions")
                    # Properly serialize dataclass to dict
                    from dataclasses import asdict
                    suggestions_dict = [asdict(s) for s in suggestions]
                    print(f"[DocumentWS] Serialized suggestions: {suggestions_dict}")
                    
                    await websocket.send_json({
                        "type": "suggestions",
                        "suggestions": suggestions_dict
                    })
                    print(f"[DocumentWS] Sent suggestions message to client")
                except Exception as e:
                    print(f"[DocumentWS] Error generating suggestions: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to generate suggestions: {str(e)}"
                    })

            elif msg_type == "update_config":
                # Client updates suggestion config
                config = data.get("config", {})
                db.update_document_suggestion_config(document_id, config)
                await websocket.send_json({"type": "config_updated", "config": config})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[DocumentWS] Error: {e}")
    finally:
        # Remove from connections
        if document_id in active_document_connections:
            active_document_connections[document_id] = [
                ws for ws in active_document_connections[document_id] if ws != websocket
            ]


@app.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str):
    """WebSocket for terminal I/O streaming."""
    await websocket.accept()

    # Add to connections
    if session_id not in active_terminal_connections:
        active_terminal_connections[session_id] = []
    active_terminal_connections[session_id].append(websocket)

    # Create observer for this session
    observer = create_terminal_observer()
    terminal_observers[session_id] = observer

    try:
        # Get terminal session info
        terminal_info = db.get_terminal_session(session_id)
        if not terminal_info:
            await websocket.send_json({"type": "error", "message": "Terminal session not found"})
            await websocket.close()
            return

        goal_id = terminal_info["goal_id"]

        # Get or create PTY session
        pty_session = await terminal_manager.get_session(session_id)
        if not pty_session:
            pty_session = await terminal_manager.create_session(
                session_id=session_id,
                working_dir=terminal_info["working_directory"]
            )

        if not pty_session:
            await websocket.send_json({"type": "error", "message": "Failed to create terminal"})
            await websocket.close()
            return

        # Set up output callback to send to WebSocket
        async def handle_output(data: str):
            try:
                await websocket.send_json({"type": "output", "data": data})
            except Exception:
                pass

        pty_session.on_output = lambda data: asyncio.create_task(handle_output(data))

        # Command parsing state
        current_command = ""
        output_buffer = ""

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "input":
                input_data = data.get("data", "")

                # Track commands (simple heuristic: input ending with newline)
                if "\n" in input_data or "\r" in input_data:
                    current_command = input_data.strip()

                await terminal_manager.write_input(session_id, input_data)

            elif msg_type == "resize":
                rows = data.get("rows", 24)
                cols = data.get("cols", 80)
                await terminal_manager.resize(session_id, rows, cols)

            elif msg_type == "command_complete":
                # Client signals command completed
                command = data.get("command", current_command)
                output = data.get("output", "")
                exit_code = data.get("exit_code", 0)

                print(f"[TerminalWS] Command complete: {command[:50]}... (exit_code={exit_code}, output_len={len(output)})")

                # Save to database
                try:
                    db.append_terminal_command(session_id, command, output, exit_code)
                except Exception as e:
                    print(f"[TerminalWS] Failed to save command to database: {e}")

                # Process observation
                try:
                    observation = observer.process_command(command, output, exit_code)
                    print(f"[TerminalWS] Observation: activity={observation.activity_type}, should_trigger={observation.should_trigger_suggestion}, priority={observation.suggestion_priority}")

                    # Check if we should trigger a suggestion
                    if observer.should_trigger_suggestion_now():
                        suggestion_context = observer.get_suggestion_context()

                        # Send observation to WebSocket
                        await websocket.send_json({
                            "type": "observation",
                            "activity": observation.activity_type,
                            "suggestion": f"Detected {observation.activity_type} activity"
                        })
                        print(f"[TerminalWS] Sent observation to client: {observation.activity_type}")

                        # Route to appropriate channels
                        try:
                            await suggestion_router.route_terminal_observation(
                                goal_id=goal_id,
                                observation=suggestion_context
                            )
                        except Exception as e:
                            print(f"[TerminalWS] Failed to route observation: {e}")
                except Exception as e:
                    print(f"[TerminalWS] Error processing observation: {e}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[TerminalWS] Error: {e}")
    finally:
        # Clean up
        if session_id in active_terminal_connections:
            active_terminal_connections[session_id] = [
                ws for ws in active_terminal_connections[session_id] if ws != websocket
            ]
        if session_id in terminal_observers:
            del terminal_observers[session_id]


@app.websocket("/ws/channel/{channel_id}")
async def channel_websocket(websocket: WebSocket, channel_id: int):
    """WebSocket for real-time channel messages and suggestions."""
    await websocket.accept()

    # Add to connections
    if channel_id not in active_channel_connections:
        active_channel_connections[channel_id] = []
    active_channel_connections[channel_id].append(websocket)

    # Register callback with suggestion router
    async def message_callback(message: dict):
        try:
            await websocket.send_json({
                "type": "message",
                "message": message
            })
        except Exception:
            pass

    suggestion_router.register_channel_callback(channel_id, message_callback)

    try:
        # Get channel info
        channel = db.get_channel_by_id(channel_id)
        if not channel:
            await websocket.send_json({"type": "error", "message": "Channel not found"})
            await websocket.close()
            return

        # Send recent messages
        messages = db.get_recent_channel_messages(channel_id, limit=20)
        await websocket.send_json({
            "type": "history",
            "messages": messages
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                # User sends a message
                content = data.get("content", "")
                role = data.get("role", "user")

                message = db.create_channel_message(
                    channel_id=channel_id,
                    role=role,
                    content=content,
                    message_type="chat",
                    source="user_input"
                )

                # Broadcast to all connected clients
                for ws in active_channel_connections.get(channel_id, []):
                    try:
                        await ws.send_json({
                            "type": "message",
                            "message": message
                        })
                    except Exception:
                        pass

            elif msg_type == "update_context":
                # User updates channel suggestion context
                context = data.get("context", {})
                updated = db.update_channel_suggestion_context(channel_id, context)
                await websocket.send_json({
                    "type": "context_updated",
                    "suggestion_context": updated["suggestion_context"] if updated else {}
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ChannelWS] Error: {e}")
    finally:
        # Clean up
        if channel_id in active_channel_connections:
            active_channel_connections[channel_id] = [
                ws for ws in active_channel_connections[channel_id] if ws != websocket
            ]
        suggestion_router.unregister_channel_callback(channel_id, message_callback)


# ============================================
# Frontend Static File Serving (must be last)
# ============================================

# Serve frontend static files (if built)
if frontend_dist.exists():
    # Serve static assets (JS, CSS, etc.)
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # Serve the frontend HTML for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes."""
        # Don't serve frontend for API routes, WebSocket, or audio
        if full_path.startswith(("api/", "ws/", "audio/", "assets/")):
            raise HTTPException(status_code=404, detail="Not found")
        # Serve index.html for all other routes (SPA routing)
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
else:
    # Frontend not built - show API info at root
    @app.get("/")
    def read_root():
        """Root endpoint - frontend not built."""
        return {
            "message": "Liminal Discovery API", 
            "version": "1.0.0", 
            "note": "Frontend not built. Build with: cd frontend && npm run build"
        }


if __name__ == "__main__":
    import uvicorn
    import os
    # Railway provides PORT env var, fallback to 8000 for local dev
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
