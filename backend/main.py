"""FastAPI application — Liminal Agent Platform."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.routers import auth, projects, runs, onboarding

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Liminal", description="Your AI that gets things done")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Mount API routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(runs.router)
app.include_router(onboarding.router)

# WebSocket routes
app.add_api_websocket_route("/ws/run/{run_id}", runs.ws_run)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend static files if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
