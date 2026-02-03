"""Project CRUD routes."""

import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import Project, Artifact, AgentRun, ChatMessage, UserProfile, get_db
from backend.services.prompt_builder import build_system_prompt, build_proactive_instruction
from backend.services.llm import chat_messages
from backend.services.mediator import mediate_extract, mediate_generate, mediate_regenerate

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
    domain: Optional[str] = None
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

    try:
        greeting_text = chat_messages(system_prompt, [{"role": "user", "content": instruction}])
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
        if not (m.role == "system" and m.content.startswith("[Background research:"))
    ]


class ChatRequest(BaseModel):
    message: Optional[str] = None


async def _run_research(task: str, timeout: float = 60.0) -> str:
    """Run a research agent and return result text. Returns empty string on failure/timeout."""
    try:
        from backend.services.claude_code_executor import executor as _executor

        instruction = (
            f"Quick background research task.\n\n"
            f"Task: {task}\n\n"
            f"Return a concise summary of what you find (2-4 bullet points). "
            f"Be specific and factual."
        )
        cmd = [
            "claude", "-p", instruction,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--system-prompt", _executor.SYSTEM_PROMPT,
            "--allowedTools", "WebSearch,WebFetch,Read,Bash",
            "--max-turns", "3",
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode != 0:
            logger.warning(f"Research process exited {process.returncode}: {stderr.decode()[:500]}")
            return ""
        for line in stdout.decode().strip().split("\n"):
            try:
                evt = json.loads(line)
                if evt.get("type") == "result":
                    return evt.get("result", "")
            except json.JSONDecodeError:
                continue
        logger.warning(f"Research: no result event found in output. stdout={stdout.decode()[:300]}")
    except asyncio.TimeoutError:
        logger.warning(f"Research timed out after {timeout}s for: {task[:100]}")
    except Exception as e:
        logger.warning(f"Background research failed: {type(e).__name__}: {e}")
    return ""


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/{project_id}/chat")
async def project_chat(project_id: int, req: ChatRequest, db: Session = Depends(get_db)):
    """Conversational mediation endpoint. Returns SSE stream with researching + message events."""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    async def _chat_stream():
        # Step 1: Extract signals (mini model, ~1s) — also detects research need
        from backend.database import get_db as _get_db
        loop = asyncio.get_event_loop()

        yield _sse_event("status", {"message": "Understanding your message…"})

        def _extract_in_thread():
            thread_db = next(_get_db())
            try:
                return mediate_extract(project_id, req.message, thread_db)
            finally:
                thread_db.close()

        extract_result = await loop.run_in_executor(None, _extract_in_thread)

        # Early return (greeting, cached)
        if extract_result.get("_early_return"):
            extract_result.pop("_early_return", None)
            yield _sse_event("message", {
                "message": extract_result.get("message", ""),
                "actions": extract_result.get("actions", []),
                "run_id": None,
            })
            return

        research_topic = extract_result.pop("_pending_research", None)
        research_text = ""

        if research_topic:
            # Emit indicator immediately — user sees it within ~1-2s (after extract only)
            yield _sse_event("researching", {"topic": research_topic})

            yield _sse_event("status", {"message": f"Researching {research_topic}…"})

            # Run research (async subprocess) and generate (sync, in thread) in parallel
            def _generate_in_thread():
                thread_db = next(_get_db())
                try:
                    return mediate_generate(extract_result, thread_db)
                finally:
                    thread_db.close()

            generate_future = loop.run_in_executor(None, _generate_in_thread)
            research_future = asyncio.ensure_future(_run_research(research_topic))

            result, research_text = await asyncio.gather(generate_future, research_future)
        else:
            yield _sse_event("status", {"message": "Composing response…"})

            # No research — just generate
            def _generate_in_thread():
                thread_db = next(_get_db())
                try:
                    return mediate_generate(extract_result, thread_db)
                finally:
                    thread_db.close()

            result = await loop.run_in_executor(None, _generate_in_thread)

        if research_text:
            # Save research as system message
            from backend.database import ChatMessage as _CM
            _db = next(_get_db())
            try:
                _db.add(_CM(
                    project_id=project_id,
                    role="system",
                    content=f"[Background research: {research_topic}]\n\n{research_text}",
                ))
                _db.commit()

                # Save research as artifact for right panel
                from backend.database import Artifact as _Art
                _db.add(_Art(
                    project_id=project_id,
                    artifact_type="research",
                    title=research_topic,
                    content={"markdown": research_text},
                    sources=[],
                ))
                _db.commit()

                # Extract insights from research results
                from backend.services.memory import extract_research_insights
                extract_research_insights(
                    project.user_id, research_topic, research_text,
                    str(project_id), _db,
                )
            finally:
                _db.close()

            # Re-generate response with research context
            yield _sse_event("status", {"message": "Incorporating research…"})
            try:
                regen = mediate_regenerate(project_id, research_topic, research_text, db)
                result["message"] = regen["message"]
                result["actions"] = regen.get("actions", result["actions"])
            except Exception as e:
                logger.warning(f"Regeneration after research failed: {e}")

        # Handle escalation
        run_id = None
        if result.get("escalate") and (result.get("task_description") or project.description):
            task_desc = result["task_description"] or f"Work on: {project.description or project.name}"
            from backend.services.run_manager import run_manager
            from backend.services.ws_manager import ws_manager

            run = AgentRun(
                project_id=project_id,
                user_id=project.user_id,
                goal=task_desc,
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            await run_manager.start_run(run.run_id, on_event=ws_manager.broadcast)
            run_id = run.run_id

        yield _sse_event("message", {
            "message": result["message"],
            "actions": result["actions"],
            "run_id": run_id,
        })

    return StreamingResponse(_chat_stream(), media_type="text/event-stream")


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
        "domain": project.domain,
        "created_at": str(project.created_at),
        "run_count": len(runs),
        "latest_run_status": latest[0].status if latest else None,
    }
