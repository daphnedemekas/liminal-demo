"""Project CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import Project, Artifact, AgentRun, get_db

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
