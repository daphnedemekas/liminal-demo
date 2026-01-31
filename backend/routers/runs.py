"""Run management routes + WebSocket for real-time events."""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import AgentRun, Project, get_db
from backend.services.run_manager import run_manager
from backend.services.event_store import event_store
from backend.services.ws_manager import ws_manager

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunCreate(BaseModel):
    project_id: int
    goal: str


class RunResponse(BaseModel):
    run_id: str
    project_id: int
    goal: str
    status: str
    current_step: int
    result_summary: str
    cost_cents: int
    created_at: str

    class Config:
        from_attributes = True


@router.post("", response_model=RunResponse)
async def create_run(req: RunCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(id=req.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    run = AgentRun(
        project_id=req.project_id,
        user_id=project.user_id,
        goal=req.goal,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    await run_manager.start_run(run.run_id, on_event=ws_manager.broadcast)

    return RunResponse(
        run_id=run.run_id,
        project_id=run.project_id,
        goal=run.goal,
        status=run.status,
        current_step=run.current_step,
        result_summary=run.result_summary,
        cost_cents=run.cost_cents,
        created_at=str(run.created_at),
    )


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(AgentRun).filter_by(run_id=run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    events = event_store.get_events(run_id, db=db)
    return {
        "run_id": run.run_id,
        "project_id": run.project_id,
        "goal": run.goal,
        "status": run.status,
        "result_summary": run.result_summary,
        "cost_cents": run.cost_cents,
        "token_usage": run.token_usage,
        "created_at": str(run.created_at),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "payload": e.payload,
                "source_url": e.source_url,
                "source_title": e.source_title,
                "timestamp": str(e.timestamp),
            }
            for e in events
        ],
    }


@router.post("/{run_id}/stop")
async def stop_run(run_id: str):
    await run_manager.stop_run(run_id)
    return {"status": "stopped"}


async def ws_run(websocket: WebSocket, run_id: str):
    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)
