"""Project CRUD routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import Project, Artifact, AgentRun, ChatMessage, UserProfile, get_db
from backend.services.prompt_builder import build_system_prompt, build_proactive_instruction
from backend.services.llm import chat
from backend.services.mediator import mediate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    user_id: str
    name: str
    description: str = ""
    involvement_level: Optional[str] = None
    budget_limit_cents: Optional[int] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    status: str
    involvement_level: Optional[str]
    budget_limit_cents: Optional[int]
    budget_spent_cents: int
    suggested_by_system: bool
    created_at: str
    run_count: int = 0
    latest_run_status: Optional[str] = None

    class Config:
        from_attributes = True


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.post("", response_model=ProjectResponse)
def create_project(req: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        user_id=req.user_id,
        name=req.name,
        description=req.description,
        involvement_level=req.involvement_level,
        budget_limit_cents=req.budget_limit_cents,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_response(db, project)


@router.get("")
def list_projects(user_id: str, db: Session = Depends(get_db)):
    projects = db.query(Project).filter_by(user_id=user_id).order_by(Project.updated_at.desc()).all()
    return [_to_response(db, p) for p in projects]


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    resp = _to_response(db, project)
    artifacts = db.query(Artifact).filter_by(project_id=project_id).order_by(Artifact.created_at.desc()).all()
    resp["artifacts"] = [
        {
            "id": a.id,
            "artifact_type": a.artifact_type,
            "title": a.title,
            "content": a.content,
            "sources": a.sources,
            "created_at": str(a.created_at),
        }
        for a in artifacts
    ]
    return resp


@router.put("/{project_id}")
def update_project(project_id: int, req: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if req.name is not None:
        project.name = req.name
    if req.description is not None:
        project.description = req.description
    db.commit()
    db.refresh(project)
    return _to_response(db, project)


@router.get("/{project_id}/greeting")
async def project_greeting(project_id: int, db: Session = Depends(get_db)):
    """Fast single-turn greeting when user opens a project."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    user = db.query(UserProfile).filter_by(id=project.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    recent_runs = (
        db.query(AgentRun)
        .filter_by(project_id=project_id)
        .order_by(AgentRun.created_at.desc())
        .limit(3)
        .all()
    )

    instruction = build_proactive_instruction(user, project, recent_runs)
    system_prompt = build_system_prompt(user, project)

    prompt = f"{system_prompt}\n\n---\n\n{instruction}"

    try:
        greeting_text = chat(prompt)
    except Exception as e:
        logger.warning(f"Greeting generation failed for project {project_id}: {e}")
        # Fallback to a simple greeting
        if recent_runs:
            greeting_text = f"Welcome back to {project.name}. Ready to pick up where we left off?"
        else:
            greeting_text = f"Let's get started on {project.name}. What would you like to do first?"

    return {"greeting": greeting_text}


@router.get("/{project_id}/messages")
def get_messages(project_id: int, db: Session = Depends(get_db)):
    """Return chat history for a project."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    msgs = (
        db.query(ChatMessage)
        .filter_by(project_id=project_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "actions": m.actions or [],
            "created_at": str(m.created_at),
        }
        for m in msgs
    ]


class ChatRequest(BaseModel):
    message: Optional[str] = None


@router.post("/{project_id}/chat")
async def project_chat(project_id: int, req: ChatRequest, db: Session = Depends(get_db)):
    """Conversational mediation endpoint. Returns a fast chat response or escalates to agent."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    result = mediate(project_id, req.message, db)

    response = {
        "message": result["message"],
        "actions": result["actions"],
        "run_id": None,
    }

    if result["escalate"] and result["task_description"]:
        from backend.services.run_manager import run_manager
        from backend.services.ws_manager import ws_manager

        run = AgentRun(
            project_id=project_id,
            user_id=project.user_id,
            goal=result["task_description"],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        await run_manager.start_run(run.run_id, on_event=ws_manager.broadcast)
        response["run_id"] = run.run_id

    return response


@router.get("/{project_id}/artifacts")
def get_artifacts(project_id: int, db: Session = Depends(get_db)):
    """Return all artifacts for a project."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    artifacts = db.query(Artifact).filter_by(project_id=project_id).order_by(Artifact.created_at.asc()).all()
    return [
        {
            "id": a.id,
            "artifact_type": a.artifact_type,
            "title": a.title,
            "content": a.content,
            "sources": a.sources,
            "created_at": str(a.created_at),
        }
        for a in artifacts
    ]


class ArtifactUpdate(BaseModel):
    content: dict


@router.patch("/{project_id}/artifacts/{artifact_id}")
def update_artifact(project_id: int, artifact_id: int, req: ArtifactUpdate, db: Session = Depends(get_db)):
    """Update artifact content (e.g. checklist toggle)."""
    artifact = db.query(Artifact).filter_by(id=artifact_id, project_id=project_id).first()
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    artifact.content = req.content
    db.commit()
    return {"status": "ok"}


def _to_response(db: Session, project: Project) -> dict:
    runs = db.query(AgentRun).filter_by(project_id=project.id).all()
    latest = sorted(runs, key=lambda r: r.created_at, reverse=True)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "involvement_level": project.involvement_level,
        "budget_limit_cents": project.budget_limit_cents,
        "budget_spent_cents": project.budget_spent_cents,
        "suggested_by_system": project.suggested_by_system,
        "created_at": str(project.created_at),
        "run_count": len(runs),
        "latest_run_status": latest[0].status if latest else None,
    }
