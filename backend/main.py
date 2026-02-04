"""FastAPI application — Envisage Agent Platform."""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.database import init_db, seed_demo_data
from backend.routers import auth, projects, runs, onboarding, discovery, context, insights
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Envisage", description="AI for human agency")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and seed demo data
init_db()
seed_demo_data()

# Cleanup any runs orphaned by previous server restart
from backend.services.run_manager import run_manager
run_manager.cleanup_orphaned_runs()

# Mount API routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(runs.router)
app.include_router(onboarding.router)
app.include_router(discovery.router)
app.include_router(context.router)
app.include_router(insights.router)

# WebSocket routes
app.add_api_websocket_route("/ws/run/{run_id}", runs.ws_run)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── TTS endpoint ─────────────────────────────────────────────────────

from pydantic import BaseModel as _BM

class _TTSRequest(_BM):
    text: str

@app.post("/api/tts")
def tts_endpoint(req: _TTSRequest):
    from backend.services.audio_service import get_audio_service
    from fastapi.responses import FileResponse
    svc = get_audio_service()
    if not svc.available:
        from fastapi import HTTPException
        raise HTTPException(501, "TTS not configured (ELEVENLABS_API_KEY not set)")
    path = svc.text_to_speech(req.text)
    return FileResponse(str(path), media_type="audio/mpeg")


# ── App Artifact Serving & Data API ──────────────────────────────────

from backend.database import Artifact, Project, UserProfile, get_session_factory


def _build_envisage_sdk(artifact_id: int, user, project) -> str:
    """Generate the Envisage SDK script tag injected into app HTML."""
    user_info = json.dumps({"name": user.name} if user else {})
    project_info = json.dumps({
        "name": project.name,
        "description": project.description or "",
    } if project else {})

    return f"""<script>
window.envisage = {{
  artifactId: {artifact_id},
  user: {user_info},
  project: {project_info},
  store: {{
    _cache: null,
    async save(data) {{
      try {{
        const res = await fetch('/api/app-data/{artifact_id}', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(data)
        }});
        if (res.ok) {{ this._cache = data; return true; }}
        console.warn('Envisage store save failed:', res.status);
        return false;
      }} catch (e) {{
        console.warn('Envisage store save error:', e);
        // Fallback to localStorage
        try {{ localStorage.setItem('envisage_app_{artifact_id}', JSON.stringify(data)); }} catch(_) {{}}
        return false;
      }}
    }},
    async load() {{
      if (this._cache) return this._cache;
      try {{
        const res = await fetch('/api/app-data/{artifact_id}');
        if (res.ok) {{
          const data = await res.json();
          if (data && Object.keys(data).length > 0) {{ this._cache = data; return data; }}
        }}
      }} catch (e) {{
        console.warn('Envisage store load error:', e);
      }}
      // Fallback to localStorage
      try {{
        const stored = localStorage.getItem('envisage_app_{artifact_id}');
        if (stored) {{ return JSON.parse(stored); }}
      }} catch(_) {{}}
      return null;
    }}
  }}
}};
</script>"""


@app.get("/app/{artifact_id}")
async def serve_app(artifact_id: int):
    """Serve an app artifact as a full HTML page with Envisage SDK injected."""
    session = get_session_factory()()
    try:
        artifact = session.query(Artifact).filter_by(
            id=artifact_id, artifact_type="app"
        ).first()
        if not artifact:
            raise HTTPException(404, "App not found")

        project = session.query(Project).filter_by(id=artifact.project_id).first()
        user = None
        if project:
            user = session.query(UserProfile).filter_by(id=project.user_id).first()

        html = artifact.content.get("html", "") if isinstance(artifact.content, dict) else ""
        sdk_script = _build_envisage_sdk(artifact_id, user, project)

        # Inject SDK before </head> or at start of document
        if "</head>" in html:
            html = html.replace("</head>", f"{sdk_script}\n</head>")
        elif "<body" in html:
            idx = html.index("<body")
            end = html.index(">", idx) + 1
            html = html[:end] + f"\n{sdk_script}" + html[end:]
        else:
            html = f"{sdk_script}\n{html}"

        return HTMLResponse(html)
    finally:
        session.close()


@app.get("/api/app-data/{artifact_id}")
async def get_app_data(artifact_id: int):
    """Load persisted app state for an artifact."""
    session = get_session_factory()()
    try:
        artifact = session.query(Artifact).filter_by(id=artifact_id).first()
        if not artifact:
            raise HTTPException(404, "App not found")
        content = artifact.content if isinstance(artifact.content, dict) else {}
        return content.get("user_data", {})
    finally:
        session.close()


@app.post("/api/app-data/{artifact_id}")
async def save_app_data(artifact_id: int, request: Request):
    """Save app state for an artifact."""
    session = get_session_factory()()
    try:
        artifact = session.query(Artifact).filter_by(id=artifact_id).first()
        if not artifact:
            raise HTTPException(404, "App not found")
        data = await request.json()
        content = dict(artifact.content) if isinstance(artifact.content, dict) else {}
        content["user_data"] = data
        artifact.content = content
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()


# Serve frontend static files if built
# Try multiple possible locations (handles different deployment layouts)
_candidates = [
    Path(__file__).parent.parent / "frontend" / "dist",  # dev: repo_root/frontend/dist
    Path.cwd() / "frontend" / "dist",                    # Railway: /app/frontend/dist
]
frontend_dist = next((p for p in _candidates if p.exists() and (p / "index.html").exists()), None)
if frontend_dist:
    logger.info(f"Serving frontend from {frontend_dist}")
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    logger.warning(f"Frontend dist not found. Checked: {[str(p) for p in _candidates]}")
