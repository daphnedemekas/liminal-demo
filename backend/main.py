"""FastAPI application — Envisage Agent Platform."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import init_db, seed_demo_data
from backend.routers import auth, projects, runs, onboarding, discovery, context, insights
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Envisage", description="AI for human agency")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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


# Serve frontend static files if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
