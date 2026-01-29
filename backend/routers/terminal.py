"""Terminal session endpoints and WebSocket handler."""
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api", tags=["terminal"])

# Database and services will be injected
_db = None
_terminal_manager = None
_terminal_observer_factory = None
_suggestion_router = None
active_terminal_connections: dict = {}
terminal_observers: dict = {}


def init_router(db, terminal_manager, terminal_observer_factory=None, suggestion_router=None):
    """Initialize router with database and services."""
    global _db, _terminal_manager, _terminal_observer_factory, _suggestion_router
    _db = db
    _terminal_manager = terminal_manager
    _terminal_observer_factory = terminal_observer_factory
    _suggestion_router = suggestion_router


class TerminalStartRequest(BaseModel):
    goal_id: int
    user_id: str
    working_directory: str = "~"


class TerminalResponse(BaseModel):
    id: int
    session_id: str
    goal_id: int
    user_id: str
    working_directory: str
    is_active: bool
    created_at: Optional[str] = None


class ChannelCreateRequest(BaseModel):
    goal_id: int
    user_id: str
    channel_type: str = "custom"
    name: str
    suggestion_context: Optional[dict] = None
    source_binding: Optional[str] = None


class ChannelContextRequest(BaseModel):
    instructions: Optional[str] = None
    focus_areas: Optional[List[str]] = None
    excluded_topics: Optional[List[str]] = None


class ChannelResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    channel_type: str
    name: str
    suggestion_context: dict
    source_binding: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class ChannelMessageResponse(BaseModel):
    id: int
    channel_id: int
    role: str
    content: str
    message_type: str
    source: Optional[str] = None
    metadata: dict
    created_at: Optional[str] = None


@router.post("/terminal/start", response_model=TerminalResponse)
async def start_terminal(request: TerminalStartRequest):
    """Initialize a terminal session."""
    try:
        session_id = str(uuid.uuid4())

        terminal = _db.create_terminal_session(
            session_id=session_id,
            goal_id=request.goal_id,
            user_id=request.user_id,
            working_directory=request.working_directory
        )

        await _terminal_manager.create_session(
            session_id=session_id,
            working_dir=request.working_directory
        )

        return TerminalResponse(**terminal)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terminal/{session_id}/history")
async def get_terminal_history(session_id: str, limit: int = 50):
    """Get command history for a terminal session."""
    try:
        history = _db.get_terminal_history(session_id, limit=limit)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Chat Channel Endpoints

@router.post("/goal/{goal_id}/channel", response_model=ChannelResponse)
async def create_channel(goal_id: int, request: ChannelCreateRequest):
    """Create a new chat channel for a goal."""
    try:
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        channel = _db.create_chat_channel(
            goal_id=request.goal_id,
            user_id=request.user_id,
            channel_type=request.channel_type,
            name=request.name,
            suggestion_context=request.suggestion_context or {},
            source_binding=request.source_binding
        )
        return ChannelResponse(**channel)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goal/{goal_id}/channels", response_model=List[ChannelResponse])
async def get_channels(goal_id: int):
    """Get all chat channels for a goal."""
    try:
        channels = _db.get_goal_channels(goal_id)
        return [ChannelResponse(**c) for c in channels]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/channel/{channel_id}/context", response_model=ChannelResponse)
async def update_channel_context(channel_id: int, request: ChannelContextRequest):
    """Update suggestion context for a channel."""
    try:
        context = {
            "instructions": request.instructions,
            "focus_areas": request.focus_areas or [],
            "excluded_topics": request.excluded_topics or []
        }
        channel = _db.update_channel_suggestion_context(channel_id, context)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return ChannelResponse(**channel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channel/{channel_id}/messages", response_model=List[ChannelMessageResponse])
async def get_channel_messages(channel_id: int, limit: int = 100, offset: int = 0):
    """Get messages for a channel."""
    try:
        messages = _db.get_channel_messages(channel_id, limit=limit, offset=offset)
        return [ChannelMessageResponse(**m) for m in messages]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_terminal_websocket_handler():
    """Return the WebSocket handler for terminal sessions."""

    async def terminal_websocket(websocket: WebSocket, session_id: str):
        """WebSocket for terminal I/O streaming."""
        await websocket.accept()

        if session_id not in active_terminal_connections:
            active_terminal_connections[session_id] = []
        active_terminal_connections[session_id].append(websocket)

        observer = None
        if _terminal_observer_factory:
            observer = _terminal_observer_factory()
            terminal_observers[session_id] = observer

        try:
            terminal_info = _db.get_terminal_session(session_id)
            if not terminal_info:
                await websocket.send_json({"type": "error", "message": "Terminal session not found"})
                await websocket.close()
                return

            goal_id = terminal_info["goal_id"]

            pty_session = await _terminal_manager.get_session(session_id)
            if not pty_session:
                pty_session = await _terminal_manager.create_session(
                    session_id=session_id,
                    working_dir=terminal_info["working_directory"]
                )

            if not pty_session:
                await websocket.send_json({"type": "error", "message": "Failed to create terminal"})
                await websocket.close()
                return

            async def handle_output(data: str):
                try:
                    await websocket.send_json({"type": "output", "data": data})
                except Exception:
                    pass

            pty_session.on_output = lambda data: asyncio.create_task(handle_output(data))

            current_command = ""
            input_line_buffer = ""  # Accumulate typed characters

            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "input":
                    input_data = data.get("data", "")

                    if "\n" in input_data or "\r" in input_data:
                        # Enter pressed — commit accumulated input as current command
                        current_command = input_line_buffer.strip()
                        input_line_buffer = ""
                    elif input_data == "\x7f" or input_data == "\b":
                        # Backspace
                        input_line_buffer = input_line_buffer[:-1]
                    elif input_data == "\x03":
                        # Ctrl+C
                        input_line_buffer = ""
                        current_command = ""
                    elif len(input_data) == 1 and input_data >= " ":
                        # Printable character
                        input_line_buffer += input_data
                    elif len(input_data) > 1 and not input_data.startswith("\x1b"):
                        # Pasted text
                        input_line_buffer += input_data

                    await _terminal_manager.write_input(session_id, input_data)

                elif msg_type == "resize":
                    rows = data.get("rows", 24)
                    cols = data.get("cols", 80)
                    await _terminal_manager.resize(session_id, rows, cols)

                elif msg_type == "command_complete":
                    command = data.get("command", current_command)
                    output = data.get("output", "")
                    exit_code = data.get("exit_code", 0)

                    print(f"[TerminalWS] Command complete: {command[:50]}... (exit_code={exit_code}, output_len={len(output)})")

                    try:
                        _db.append_terminal_command(session_id, command, output, exit_code)
                    except Exception as e:
                        print(f"[TerminalWS] Failed to save command to database: {e}")

                    if observer:
                        try:
                            observation = observer.process_command(command, output, exit_code)
                            print(f"[TerminalWS] Observation: activity={observation.activity_type}, should_trigger={observation.should_trigger_suggestion}, priority={observation.suggestion_priority}")

                            if observer.should_trigger_suggestion_now():
                                suggestion_context = observer.get_suggestion_context()

                                # Build a meaningful suggestion message
                                suggestion_parts = []
                                if observation.is_error and observation.error_summary:
                                    suggestion_parts.append(f"Error detected: {observation.error_summary}")
                                if observation.learning_opportunity:
                                    suggestion_parts.append(f"Learning opportunity: {observation.learning_opportunity}")
                                if observation.understanding_signal == "struggling":
                                    suggestion_parts.append("It looks like you're hitting some friction — the chat can help break this down.")
                                elif observation.understanding_signal == "exploring":
                                    suggestion_parts.append("Looks like you're exploring — want a deeper explanation of what you're finding?")
                                if observation.topics_detected:
                                    suggestion_parts.append(f"Topics: {', '.join(observation.topics_detected)}")

                                suggestion_text = " · ".join(suggestion_parts) if suggestion_parts else f"Detected {observation.activity_type} activity"

                                await websocket.send_json({
                                    "type": "observation",
                                    "activity": observation.activity_type,
                                    "suggestion": suggestion_text,
                                    "is_error": observation.is_error,
                                    "learning_opportunity": observation.learning_opportunity,
                                    "understanding_signal": observation.understanding_signal,
                                    "topics": observation.topics_detected,
                                    "command": observation.command[:100],
                                })
                                print(f"[TerminalWS] Sent observation to client: {observation.activity_type} - {suggestion_text[:80]}")

                                if _suggestion_router:
                                    try:
                                        await _suggestion_router.route_terminal_observation(
                                            goal_id=goal_id,
                                            observation=suggestion_context
                                        )
                                    except Exception as e:
                                        print(f"[TerminalWS] Failed to route observation: {e}")
                        except Exception as e:
                            print(f"[TerminalWS] Error processing observation: {e}")

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[TerminalWS] Error: {e}")
        finally:
            if session_id in active_terminal_connections:
                active_terminal_connections[session_id] = [
                    ws for ws in active_terminal_connections[session_id] if ws != websocket
                ]
            if session_id in terminal_observers:
                del terminal_observers[session_id]

    return terminal_websocket


def get_channel_websocket_handler():
    """Return the WebSocket handler for channel sessions."""
    active_channel_connections: dict = {}

    async def channel_websocket(websocket: WebSocket, channel_id: int):
        """WebSocket for real-time channel messages and suggestions."""
        await websocket.accept()

        if channel_id not in active_channel_connections:
            active_channel_connections[channel_id] = []
        active_channel_connections[channel_id].append(websocket)

        async def message_callback(message: dict):
            try:
                await websocket.send_json({
                    "type": "message",
                    "message": message
                })
            except Exception:
                pass

        if _suggestion_router:
            _suggestion_router.register_channel_callback(channel_id, message_callback)

        try:
            channel = _db.get_channel_by_id(channel_id)
            if not channel:
                await websocket.send_json({"type": "error", "message": "Channel not found"})
                await websocket.close()
                return

            messages = _db.get_recent_channel_messages(channel_id, limit=20)
            await websocket.send_json({
                "type": "history",
                "messages": messages
            })

            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "message":
                    content = data.get("content", "")
                    role = data.get("role", "user")

                    message = _db.create_channel_message(
                        channel_id=channel_id,
                        role=role,
                        content=content,
                        message_type="chat",
                        source="user_input"
                    )

                    for ws in active_channel_connections.get(channel_id, []):
                        try:
                            await ws.send_json({
                                "type": "message",
                                "message": message
                            })
                        except Exception:
                            pass

                elif msg_type == "update_context":
                    context = data.get("context", {})
                    updated = _db.update_channel_suggestion_context(channel_id, context)
                    await websocket.send_json({
                        "type": "context_updated",
                        "suggestion_context": updated["suggestion_context"] if updated else {}
                    })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[ChannelWS] Error: {e}")
        finally:
            if channel_id in active_channel_connections:
                active_channel_connections[channel_id] = [
                    ws for ws in active_channel_connections[channel_id] if ws != websocket
                ]
            if _suggestion_router:
                _suggestion_router.unregister_channel_callback(channel_id, message_callback)

    return channel_websocket
