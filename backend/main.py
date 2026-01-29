"""FastAPI application for Liminal Discovery System."""
import sys
import uuid
import os
from pathlib import Path

# Load environment variables from .env file (only if it exists, for local development)
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)
else:
    load_dotenv(override=False)

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.services.session_manager import session_manager
from backend.services.audio_service import get_audio_service
from backend.models.api_models import (
    SessionCreateRequest,
    SessionCreateResponse,
)

app = FastAPI(title="Liminal Discovery API")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for serving audio
audio_service = get_audio_service()
app.mount("/audio", StaticFiles(directory=str(audio_service.audio_dir)), name="audio")

# Store frontend path for later (will be mounted after all API routes)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

# ============================================
# Database Initialization
# ============================================

from src.database.manager import DatabaseManager

db_path = os.getenv("DATABASE_PATH", "data/liminal.db")
print(f"[Backend] Initializing SQLite database at {db_path}...")
db = DatabaseManager(db_path=db_path)
print(f"[Backend] Database initialized successfully")

# ============================================
# Import Services
# ============================================

from backend.services.terminal_manager import terminal_manager
from backend.services.terminal_observer import create_terminal_observer
from backend.services.document_suggestion import document_suggestion_service
from backend.services.suggestion_router import create_suggestion_router

# Initialize suggestion router with database
suggestion_router = create_suggestion_router(db)

# ============================================
# Import and Initialize Routers
# ============================================

from backend.routers import auth, discovery, teaching, feed, terminal, documents, trajectory

# Initialize routers with dependencies
auth.init_router(db)
trajectory.init_router(db)
feed.init_router(db)
teaching.init_router(db, audio_service)
discovery.init_router(db, session_manager, audio_service)
documents.init_router(db, document_suggestion_service, suggestion_router)
terminal.init_router(db, terminal_manager, create_terminal_observer, suggestion_router)

# Include routers
app.include_router(auth.router)
app.include_router(trajectory.router)
app.include_router(feed.router)
app.include_router(teaching.router)
app.include_router(documents.router)
app.include_router(terminal.router)

# ============================================
# Discovery Session Start Endpoint (Special handling)
# ============================================

@app.post("/api/discovery/start", response_model=SessionCreateResponse)
async def start_discovery(request: SessionCreateRequest = SessionCreateRequest()):
    """Create a new discovery session or resume an existing one."""
    try:
        conversation_history = []
        schema_state = None
        profile_summary = None
        is_resumed = False

        # Check if resuming a goal session
        if request.goal_id and request.user_id:
            existing = db.get_session_for_goal(request.goal_id)
            if existing and existing.get("session_id"):
                session_id = existing["session_id"]
                conversation_history = existing.get("conversation_history", [])
                schema_state = existing.get("schema_state")
                profile_summary = existing.get("profile_summary")
                is_resumed = True
                print(f"[Discovery] Resuming goal session: {session_id[:8]}... ({len(conversation_history)} messages)")

        # Check if resuming exploration session
        elif request.user_id and not request.goal:
            exploration = db.get_or_create_exploration_session(request.user_id)
            if not exploration.get("is_new"):
                session_id = exploration["session_id"]
                conversation_history = exploration.get("conversation_history", [])
                schema_state = exploration.get("schema_state")
                profile_summary = exploration.get("profile_summary")
                is_resumed = True
                print(f"[Discovery] Resuming exploration session: {session_id[:8]}... ({len(conversation_history)} messages)")

        # Generate new session if not resuming
        if not is_resumed:
            session_id = str(uuid.uuid4())
            print(f"[Discovery] Creating new session: {session_id[:8]}...")

            exploration_history = None
            if request.goal_id and request.user_id:
                db.create_session_with_type(session_id, request.user_id, 'goal', request.goal_id)
                exploration = db.get_user_exploration_session(request.user_id)
                if exploration and exploration.get("conversation_history"):
                    exploration_history = exploration.get("conversation_history", [])
                    exploration_history = exploration_history[-10:] if len(exploration_history) > 10 else exploration_history
                    print(f"[Discovery] Including {len(exploration_history)} messages from exploration chat for goal context")
            elif request.user_id:
                db.create_session_with_type(session_id, request.user_id, 'exploration')

        # Create/resume session in memory
        session_data = await session_manager.create_session(
            session_id,
            debug=False,
            model_config=request.models,
            user_goal=request.goal,
            user_id=request.user_id,
            conversation_history=conversation_history if is_resumed else None,
            schema_state=schema_state if is_resumed else None,
            exploration_history=exploration_history if not is_resumed and request.goal_id else None
        )

        # Get opening question for new sessions OR resumed sessions with no history
        opening_message = ""
        audio_url = None
        needs_opening = not is_resumed or len(conversation_history) == 0

        if needs_opening:
            opening_message = session_data.discovery_session.start()
            audio_url = None

        return SessionCreateResponse(
            session_id=session_id,
            opening_message=opening_message,
            audio_url=audio_url,
            conversation_history=conversation_history,
            is_resumed=is_resumed,
            profile_summary=profile_summary
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# Discovery schema endpoint
@app.get("/api/discovery/{session_id}/schema")
async def get_discovery_schema(session_id: str):
    """Get current discovery schema for debugging."""
    from fastapi import HTTPException
    session_data = await session_manager.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    schema = session_data.discovery_session.get_schema()
    return schema


# ============================================
# WebSocket Endpoints
# ============================================

# Get WebSocket handlers from routers
discovery_ws_handler = discovery.get_discovery_websocket_handler()
teaching_ws_handler = teaching.get_teaching_websocket_handler()
document_ws_handler = documents.get_document_websocket_handler()
terminal_ws_handler = terminal.get_terminal_websocket_handler()
channel_ws_handler = terminal.get_channel_websocket_handler()


@app.websocket("/ws/discovery/{session_id}")
async def discovery_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for discovery phase conversation."""
    await discovery_ws_handler(websocket, session_id)


@app.websocket("/ws/teaching/{session_id}")
async def teaching_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for teaching curriculum conversation."""
    await teaching_ws_handler(websocket, session_id)


@app.websocket("/ws/document/{document_id}")
async def document_websocket(websocket: WebSocket, document_id: int):
    """WebSocket for real-time document sync and AI suggestions."""
    await document_ws_handler(websocket, document_id)


@app.websocket("/ws/terminal/{session_id}")
async def terminal_websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for terminal I/O streaming."""
    await terminal_ws_handler(websocket, session_id)


@app.websocket("/ws/channel/{channel_id}")
async def channel_websocket(websocket: WebSocket, channel_id: int):
    """WebSocket for real-time channel messages and suggestions."""
    await channel_ws_handler(websocket, channel_id)


# ============================================
# Frontend Static File Serving (must be last)
# ============================================

# Serve frontend static files (if built)
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React frontend for all non-API routes."""
        # Skip API routes
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        # Try to serve the specific file first
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for client-side routing
        return FileResponse(frontend_dist / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
