"""Google Calendar OAuth2 integration.

Handles the OAuth2 flow for Google Calendar read-only access:
- Generate auth URL for user consent
- Exchange auth code for tokens
- Refresh expired tokens
- Read calendar events
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/api/integrations/google/callback",
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# Read-only scope — we only need to see events, not modify them
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def is_configured() -> bool:
    """Check if Google OAuth credentials are set."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_auth_url(user_id: str) -> str:
    """Generate the Google OAuth2 consent URL.

    The user_id is passed as state to identify the user on callback.
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # get refresh token
        "prompt": "consent",  # always show consent to get refresh token
        "state": user_id,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat(),
        "token_type": data.get("token_type", "Bearer"),
    }


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "access_token": data["access_token"],
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat(),
    }


def _token_is_expired(token_data: dict) -> bool:
    """Check if the access token has expired (with 5-minute buffer)."""
    expires_at = token_data.get("expires_at")
    if not expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(expires_at)
        return datetime.now(timezone.utc) > expiry - timedelta(minutes=5)
    except (ValueError, TypeError):
        return True


async def get_valid_token(token_data: dict) -> Optional[dict]:
    """Get a valid access token, refreshing if needed.

    Returns updated token_data dict (caller should save it).
    Returns None if refresh fails.
    """
    if not _token_is_expired(token_data):
        return token_data

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    try:
        refreshed = await refresh_access_token(refresh_token)
        token_data["access_token"] = refreshed["access_token"]
        token_data["expires_at"] = refreshed["expires_at"]
        return token_data
    except Exception as e:
        logger.warning(f"Failed to refresh Google token: {e}")
        return None


async def get_upcoming_events(
    access_token: str,
    max_results: int = 20,
    days_ahead: int = 7,
) -> list[dict]:
    """Fetch upcoming calendar events.

    Returns a simplified list of events with start, end, summary, and location.
    """
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    params = {
        "calendarId": "primary",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GOOGLE_CALENDAR_API}/calendars/primary/events",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()

    events = []
    for item in data.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})
        events.append({
            "summary": item.get("summary", "(No title)"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": item.get("location"),
            "all_day": "date" in start and "dateTime" not in start,
        })

    return events


def save_tokens(user, token_data: dict, db) -> None:
    """Save Google Calendar tokens to user's connected_sources."""
    sources = list(user.connected_sources or [])

    # Remove existing Google Calendar entry if present
    sources = [s for s in sources if s.get("type") != "google_calendar"]

    sources.append({
        "type": "google_calendar",
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "tokens": token_data,
    })

    user.connected_sources = sources
    db.commit()


def get_tokens(user) -> Optional[dict]:
    """Retrieve Google Calendar tokens from user's connected_sources."""
    for source in (user.connected_sources or []):
        if source.get("type") == "google_calendar":
            return source.get("tokens")
    return None


def is_connected(user) -> bool:
    """Check if user has Google Calendar connected."""
    return get_tokens(user) is not None
