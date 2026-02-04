"""Integration routes: Google Calendar OAuth and other connected services."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import UserProfile, get_db
from backend.services import google_calendar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class IntegrationStatus(BaseModel):
    google_calendar: bool
    # Future integrations
    oura: bool = False
    notion: bool = False


# ── Status ─────────────────────────────────────────────────────────

@router.get("/status/{user_id}")
def get_integration_status(user_id: str, db: Session = Depends(get_db)):
    """Return which integrations are connected for this user."""
    user = db.query(UserProfile).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    return {
        "google_calendar": {
            "connected": google_calendar.is_connected(user),
            "available": google_calendar.is_configured(),
        },
        "oura": {"connected": False, "available": False},
        "notion": {"connected": False, "available": False},
    }


# ── Google Calendar OAuth ──────────────────────────────────────────

@router.get("/google/auth")
def google_auth(user_id: str = Query(...)):
    """Redirect user to Google OAuth consent screen."""
    if not google_calendar.is_configured():
        raise HTTPException(
            503,
            "Google Calendar integration not configured. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.",
        )

    auth_url = google_calendar.get_auth_url(user_id)
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback. Exchanges code for tokens and saves them."""
    if error:
        logger.warning(f"Google OAuth error: {error}")
        # Redirect back to app with error
        return RedirectResponse("/?integration_error=google_denied")

    if not code or not state:
        raise HTTPException(400, "Missing code or state parameter")

    user_id = state
    user = db.query(UserProfile).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    try:
        token_data = await google_calendar.exchange_code(code)
        google_calendar.save_tokens(user, token_data, db)
        logger.info(f"Google Calendar connected for user {user_id}")
        # Redirect back to app with success
        return RedirectResponse("/?integration_success=google_calendar")
    except Exception as e:
        logger.exception(f"Google OAuth token exchange failed: {e}")
        return RedirectResponse("/?integration_error=google_failed")


@router.post("/google/disconnect")
def google_disconnect(user_id: str, db: Session = Depends(get_db)):
    """Disconnect Google Calendar for a user."""
    user = db.query(UserProfile).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    sources = list(user.connected_sources or [])
    user.connected_sources = [s for s in sources if s.get("type") != "google_calendar"]
    db.commit()

    return {"status": "disconnected"}


# ── Google Calendar data ───────────────────────────────────────────

@router.get("/google/events/{user_id}")
async def get_google_events(
    user_id: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Fetch upcoming calendar events for a connected user."""
    user = db.query(UserProfile).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    token_data = google_calendar.get_tokens(user)
    if not token_data:
        raise HTTPException(400, "Google Calendar not connected")

    # Refresh token if needed
    updated = await google_calendar.get_valid_token(token_data)
    if not updated:
        # Token refresh failed — user needs to re-authenticate
        raise HTTPException(401, "Google Calendar token expired. Please reconnect.")

    # Save refreshed tokens if they changed
    if updated["access_token"] != token_data.get("access_token"):
        google_calendar.save_tokens(user, updated, db)

    try:
        events = await google_calendar.get_upcoming_events(
            updated["access_token"],
            days_ahead=days,
        )
        return {"events": events}
    except Exception as e:
        logger.exception(f"Failed to fetch calendar events: {e}")
        raise HTTPException(502, f"Failed to fetch calendar events: {e}")
