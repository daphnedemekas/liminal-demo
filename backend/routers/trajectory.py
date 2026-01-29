"""Trajectory and progress tracking endpoints."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["trajectory"])

# Database instance will be injected
_db = None


def init_router(db):
    """Initialize router with database instance."""
    global _db
    _db = db


@router.get("/trajectory/{user_id}")
async def get_trajectory(user_id: str):
    """Get (or initialize) the user's cross-phase learner trajectory dashboard JSON."""
    try:
        traj = _db.get_or_create_learner_trajectory(user_id)
        return traj.get("dashboard_state") or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trajectory/{user_id}/refresh")
async def refresh_trajectory(user_id: str):
    """Incrementally refresh the user's trajectory dashboard from new checkpoints."""
    try:
        from src.agents.trajectory_updater import TrajectoryUpdater

        updater = TrajectoryUpdater(db=_db)
        dashboard = updater.refresh(user_id=user_id)
        return dashboard
    except Exception as e:
        import traceback
        print(f"[Trajectory Refresh Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goal/{goal_id}/progress")
async def get_goal_progress(goal_id: int, user_id: str):
    """Get detailed progress data for a specific goal."""
    try:
        goal = _db.get_goal_by_id(goal_id)
        if not goal or goal.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Goal not found")

        sessions = _db.list_sessions_for_goal(goal_id)
        teaching_sessions = [s for s in sessions if s.get("session_type") == "teaching"]

        teaching_candidate_data = goal.get("teaching_candidate")
        curriculum_tasks = None

        if isinstance(teaching_candidate_data, list) and len(teaching_candidate_data) > 0:
            curriculum_tasks = sorted(teaching_candidate_data, key=lambda x: x.get('id', x.get('index', 0)))
        elif isinstance(teaching_candidate_data, dict):
            curriculum_tasks = [teaching_candidate_data]

        print(f"[Goal Progress] Goal {goal_id}: teaching_sessions={len(teaching_sessions)}, curriculum_tasks={len(curriculum_tasks) if curriculum_tasks else 0}")

        checkpoints = []
        for session in sessions:
            session_checkpoints = _db.list_trajectory_checkpoints_for_session(session["session_id"])
            for cp in session_checkpoints:
                cp["session_id"] = session["session_id"]
            checkpoints.extend(session_checkpoints)

        checkpoints.sort(key=lambda x: x.get("created_at") or "")

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

        total_sessions = len(teaching_sessions)
        completed_sessions = sum(1 for s in teaching_sessions if s.get("status") == "completed")
        progress_pct = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0

        return {
            "goal": goal,
            "sessions": teaching_sessions,
            "curriculum": curriculum_tasks,
            "progress_percentage": progress_pct,
            "temporal_data": temporal_data,
            "current_metrics": temporal_data[-1] if temporal_data else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teaching/{session_id}/detail")
async def get_teaching_detail(session_id: str, user_id: str):
    """Get detailed view of a single teaching session with temporal progress."""
    try:
        from src.trajectory.metrics import compute_all_aggregates

        session = _db.get_session_by_id(session_id)
        if not session or session.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Session not found")

        schema_state = session.get("schema_state", {})
        curriculum_plan = schema_state.get("curriculum_plan", {})
        understanding_markers = schema_state.get("understanding_markers", {})

        checkpoints = _db.list_trajectory_checkpoints_for_session(session_id)

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
