"""Discovery routes: domain-based agency discovery flow."""

import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import UserProfile, get_db
from backend.services.discovery_engine import discovery_engine, DOMAIN_OPTIONS, infer_phase
from backend.database import DiscoveryDomain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class SelectDomainsRequest(BaseModel):
    user_id: str
    domains: list[str]


class RespondRequest(BaseModel):
    user_id: str
    message: str
    domain: Optional[str] = None


class ActivateDomainRequest(BaseModel):
    user_id: str
    domain: str


class AcceptProjectsRequest(BaseModel):
    user_id: str
    project_indices: list[int]


class UserIdRequest(BaseModel):
    user_id: str


class RunAgentRequest(BaseModel):
    user_id: str
    agent_task: str


@router.get("/options")
def get_domain_options():
    """Return the list of available domains for selection."""
    return DOMAIN_OPTIONS


@router.post("/select-domains")
def select_domains(req: SelectDomainsRequest, db: Session = Depends(get_db)):
    """Record selected domains and return opening message for the first one."""
    user = db.query(UserProfile).filter_by(id=req.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    try:
        result = discovery_engine.select_domains(req.user_id, req.domains, db)
        return result
    except Exception as e:
        logger.exception(f"select_domains failed: {e}")
        raise HTTPException(500, str(e))


@router.get("/state")
def get_state(user_id: str, db: Session = Depends(get_db)):
    """Return current discovery state for the user."""
    try:
        return discovery_engine.get_state(user_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/activate-domain")
def activate_domain(req: ActivateDomainRequest, db: Session = Depends(get_db)):
    """Activate a specific domain and return its opening or last message."""
    try:
        return discovery_engine.activate_domain(req.user_id, req.domain, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception(f"activate_domain failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/respond")
async def respond(req: RespondRequest, db: Session = Depends(get_db)):
    """Process a user response in the active domain conversation. Returns SSE stream."""
    # Handle agent_run: action from user clicking a research button (no SSE needed)
    if req.message.startswith("agent_run:"):
        try:
            result = await discovery_engine.run_agent_task(req.user_id, req.message[len("agent_run:"):], db)
            return result
        except ValueError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            logger.exception(f"run_agent_task failed: {e}")
            raise HTTPException(500, str(e))

    async def _respond_stream():
        try:
            yield _sse_event("status", {"message": "Understanding your message…"})

            result = discovery_engine.process_response(req.user_id, req.message, db, domain_name=req.domain)

            # Signal-based research: proper noun lookup from signal extraction
            pending_research = result.pop("_pending_research", None)
            if pending_research:
                yield _sse_event("status", {"message": f"Researching {pending_research}…"})
                try:
                    research_text = await asyncio.wait_for(
                        discovery_engine.run_agent_task(req.user_id, pending_research, db),
                        timeout=60.0,
                    )
                    if research_text.get("message"):
                        from backend.services.memory import extract_research_insights
                        user = db.query(UserProfile).filter_by(id=req.user_id).first()
                        if user:
                            active = db.query(DiscoveryDomain).filter_by(user_id=req.user_id, domain=req.domain).first() or \
                                     db.query(DiscoveryDomain).filter_by(user_id=req.user_id, status="active").first()
                            extract_research_insights(
                                user.id, pending_research, research_text["message"],
                                active.domain if active else None, db,
                            )
                except asyncio.TimeoutError:
                    logger.warning(f"Signal-based research timed out: {pending_research[:60]}")
                except Exception as e:
                    logger.warning(f"Signal-based research failed: {e}")

            # If the LLM requested agent research and gating passed, run with timeout
            pending = result.pop("_pending_agent", None)
            if pending:
                yield _sse_event("status", {"message": f"Researching {pending[:60]}…"})
                try:
                    researched = await asyncio.wait_for(
                        discovery_engine.run_agent_task(req.user_id, pending, db),
                        timeout=30.0,
                    )
                    researched["message"] = f"🔍 *Researched: {pending}*\n\n{researched['message']}"
                    result = researched
                except asyncio.TimeoutError:
                    logger.warning(f"Auto-research timed out after 30s: {pending[:60]}")
                except Exception as e:
                    logger.warning(f"Auto-research failed: {e}")

            # When proposing projects, auto-research existing solutions first
            if result.get("proposed_projects"):
                yield _sse_event("status", {"message": "Researching existing solutions…"})
                try:
                    result = await asyncio.wait_for(
                        discovery_engine.research_and_refine_proposals(
                            req.user_id, result, db
                        ),
                        timeout=45.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Proposal research timed out, using unresearched proposals")
                except Exception as e:
                    logger.warning(f"Proposal research failed, using unresearched proposals: {e}")

            yield _sse_event("message", result)
        except ValueError as e:
            yield _sse_event("error", {"detail": str(e)})
        except Exception as e:
            logger.exception(f"respond failed: {e}")
            yield _sse_event("error", {"detail": str(e)})

    return StreamingResponse(_respond_stream(), media_type="text/event-stream")


@router.post("/accept-projects")
def accept_projects(req: AcceptProjectsRequest, db: Session = Depends(get_db)):
    """Create projects from proposals and advance to next domain."""
    try:
        return discovery_engine.accept_projects(req.user_id, req.project_indices, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception(f"accept_projects failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/skip-domain")
def skip_domain(req: UserIdRequest, db: Session = Depends(get_db)):
    """Skip the current active domain and move to the next."""
    try:
        return discovery_engine.skip_domain(req.user_id, db)
    except Exception as e:
        logger.exception(f"skip_domain failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/run-agent")
async def run_discovery_agent(req: RunAgentRequest, db: Session = Depends(get_db)):
    """Run an agent task during discovery and return next message."""
    try:
        return await discovery_engine.run_agent_task(req.user_id, req.agent_task, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception(f"run_discovery_agent failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/complete")
def complete_discovery(req: UserIdRequest, db: Session = Depends(get_db)):
    """Finalize discovery and generate user model."""
    try:
        return discovery_engine.complete_discovery(req.user_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        logger.exception(f"complete_discovery failed: {e}")
        raise HTTPException(500, str(e))
