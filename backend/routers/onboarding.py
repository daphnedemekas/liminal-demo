"""Onboarding routes — domain selection and discovery completion."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import UserProfile, DiscoveryDomain, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class SelectDomainsRequest(BaseModel):
    user_id: str
    domains: list[str]


class CompleteRequest(BaseModel):
    user_id: str
    onboarding_info: Optional[dict] = None


@router.post("/select-domains")
def select_domains(req: SelectDomainsRequest, db: Session = Depends(get_db)):
    """Save the domains the user selected during onboarding."""
    user = db.query(UserProfile).filter_by(id=req.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.selected_domains = req.domains

    # Also create DiscoveryDomain records so navigation routing can reference them
    for domain in req.domains:
        existing = db.query(DiscoveryDomain).filter_by(user_id=req.user_id, domain=domain).first()
        if not existing:
            db.add(DiscoveryDomain(user_id=req.user_id, domain=domain, status="pending"))

    db.commit()

    return {
        "domains": [
            {"domain": d, "label": d, "status": "pending"}
            for d in req.domains
        ]
    }


@router.post("/complete")
def complete_discovery(req: CompleteRequest, db: Session = Depends(get_db)):
    """Mark onboarding/discovery as complete for a user."""
    user = db.query(UserProfile).filter_by(id=req.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.discovery_complete = True

    if req.onboarding_info:
        user.onboarding_info = json.dumps(req.onboarding_info)

    db.commit()

    return {"status": "ok", "model_summary": user.model_summary or ""}
