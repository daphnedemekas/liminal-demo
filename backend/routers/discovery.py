"""Discovery routes: domain-based agency discovery flow."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import UserProfile, get_db
from backend.services.discovery_engine import discovery_engine, DOMAIN_OPTIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class SelectDomainsRequest(BaseModel):
    user_id: str
    domains: list[str]


class RespondRequest(BaseModel):
    user_id: str
    message: str


class AcceptProjectsRequest(BaseModel):
    user_id: str
    project_indices: list[int]


class UserIdRequest(BaseModel):
    user_id: str


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


@router.post("/respond")
def respond(req: RespondRequest, db: Session = Depends(get_db)):
    """Process a user response in the active domain conversation."""
    try:
        return discovery_engine.process_response(req.user_id, req.message, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception(f"respond failed: {e}")
        raise HTTPException(500, str(e))


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


@router.post("/complete")
def complete_discovery(req: UserIdRequest, db: Session = Depends(get_db)):
    """Finalize discovery and generate user model."""
    try:
        return discovery_engine.complete_discovery(req.user_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception(f"complete_discovery failed: {e}")
        raise HTTPException(500, str(e))
