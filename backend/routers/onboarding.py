"""Onboarding routes: quick context, Q&A, suggestions."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.onboarding_orchestrator import onboarding, QUICK_CONTEXT_OPTIONS

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class QuickContextRequest(BaseModel):
    user_id: str
    selected_ids: list[str]


class AnswerRequest(BaseModel):
    user_id: str
    answer: str


class AcceptSuggestionsRequest(BaseModel):
    user_id: str
    indices: list[int]


class SkipRequest(BaseModel):
    user_id: str


@router.get("/options")
def get_options():
    """Return the quick-context multiple-choice options."""
    return QUICK_CONTEXT_OPTIONS


@router.get("/state/{user_id}")
def get_state(user_id: str):
    """Get current onboarding state."""
    return onboarding.get_state(user_id)


@router.post("/context")
def submit_context(req: QuickContextRequest):
    """Submit quick-context selections."""
    return onboarding.submit_quick_context(req.user_id, req.selected_ids)


@router.post("/next-question")
async def get_next_question(req: SkipRequest):
    """Generate a single adaptive follow-up question."""
    question = await onboarding.generate_next_question(req.user_id)
    return {"question": question}


@router.post("/answer")
async def submit_answer(req: AnswerRequest):
    """Process a user's answer and extract signals."""
    result = await onboarding.process_answer(req.user_id, req.answer)
    return result


@router.post("/suggestions")
async def get_suggestions(req: SkipRequest):
    """Generate project suggestions from gathered signals."""
    suggestions = await onboarding.generate_suggestions(req.user_id)
    return {"suggestions": suggestions}


@router.post("/accept")
def accept_suggestions(req: AcceptSuggestionsRequest):
    """Accept selected suggestions and complete onboarding."""
    created = onboarding.accept_suggestions(req.user_id, req.indices)
    return {"created_projects": created}


@router.post("/skip")
def skip(req: SkipRequest):
    """Skip onboarding entirely."""
    onboarding.skip_onboarding(req.user_id)
    return {"status": "skipped"}
