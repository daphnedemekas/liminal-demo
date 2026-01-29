"""Discovery session endpoints and WebSocket handler."""
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api", tags=["discovery"])

# Database and services will be injected
_db = None
_session_manager = None
_audio_service = None


def init_router(db, session_manager, audio_service=None):
    """Initialize router with database and session manager."""
    global _db, _session_manager, _audio_service
    _db = db
    _session_manager = session_manager
    _audio_service = audio_service


def get_discovery_websocket_handler():
    """Return the WebSocket handler for discovery sessions."""

    async def discovery_websocket(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for discovery phase conversation with streaming support."""
        await websocket.accept()

        _ws_closed = False

        async def safe_send(data: dict):
            """Send JSON to websocket, silently ignoring if connection is already closed."""
            nonlocal _ws_closed
            if _ws_closed:
                return
            try:
                await websocket.send_json(data)
            except Exception:
                _ws_closed = True

        session_data = await _session_manager.get_session(session_id)
        if not session_data:
            await websocket.send_json({"type": "error", "message": "Session not found"})
            await websocket.close()
            return

        try:
            session_info = _db.get_session_by_id(session_id) or {}
        except Exception:
            session_info = {}

        def _maybe_checkpoint():
            """Persist a sparse trajectory checkpoint for this user (best-effort)."""
            print(f"[Trajectory] _maybe_checkpoint called for session {session_id[:8]}...")
            try:
                discovery = session_data.discovery_session
                if not discovery:
                    print(f"[Trajectory] No discovery session found, skipping checkpoint")
                    return
                schema_snapshot = discovery.get_schema()
                turns = (schema_snapshot.get("interview_state", {}) or {}).get("turns_elapsed")
                user_id_val = getattr(discovery, "user_id", None) or session_info.get("user_id")
                print(f"[Trajectory] Calling checkpoint writer for user {user_id_val[:8] if user_id_val else 'None'}... at turn {turns}")
                checkpoint_id = _db.maybe_write_trajectory_checkpoint(
                    user_id=user_id_val,
                    session_id=session_id,
                    session_type=session_info.get("session_type") or "exploration",
                    goal_id=session_info.get("goal_id"),
                    teaching_candidate_id=session_info.get("teaching_candidate_id"),
                    schema_state=schema_snapshot,
                    conversation_history=getattr(discovery, "conversation_history", None),
                    turn_index=turns,
                )
                if checkpoint_id:
                    print(f"[Trajectory] Checkpoint {checkpoint_id} written at turn {turns}")
                else:
                    print(f"[Trajectory] No checkpoint needed (turn {turns}, cadence or event condition not met)")
            except Exception as e:
                print(f"[Trajectory] Discovery checkpoint failed: {e}")
                import traceback
                traceback.print_exc()

        try:
            while True:
                print(f"[WebSocket] Waiting for message on session {session_id[:8]}...")
                data = await websocket.receive_json()
                print(f"[WebSocket] Received data: {data}")
                user_message = data.get("content", "")

                if not user_message:
                    continue

                status_message = "Analyzing your response..."
                await websocket.send_json({
                    "type": "status",
                    "status": status_message
                })

                try:
                    is_explicit_command = user_message.startswith("__") and user_message.endswith("__")

                    is_onboarding_message = False
                    if user_message.startswith("__ONBOARDING__"):
                        background_info = user_message.replace("__ONBOARDING__", "", 1)
                        user_message = background_info
                        is_onboarding_message = True
                        print(f"[WebSocket] Onboarding message detected - will use for context but not add to visible history")

                    # Handle special commands
                    if user_message == "__ACCEPT_GOAL__":
                        await safe_send({"type": "status", "status": ""})
                        result = session_data.discovery_session.accept_proposed_goal()

                        if "error" in result:
                            await safe_send({"type": "error", "message": result["error"]})
                            continue

                        if "error" in result or not result.get("success"):
                            await safe_send({
                                "type": "error",
                                "message": result.get("error") or result.get("message", "Failed to accept goal")
                            })
                            continue

                        await safe_send({
                            "type": "create_goal_panel",
                            "goal": result.get("goal", ""),
                            "goal_id": result.get("goal_id", 0),
                            "message": result.get("message", "Goal accepted")
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__REJECT_GOAL__":
                        await safe_send({"type": "status", "status": ""})
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(
                            None,
                            session_data.discovery_session.reject_proposed_goal
                        )
                        await safe_send({
                            "type": "message",
                            "content": response,
                            "audio_url": None
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__GENERATE_LEARNING_PATH__":
                        await safe_send({"type": "status", "status": ""})
                        result = session_data.discovery_session.generate_learning_path()

                        if not result.get("success"):
                            await safe_send({
                                "type": "error",
                                "message": result.get("message", "Failed to generate learning path")
                            })
                            continue

                        if session_data.discovery_session.schema.task_curriculum.proposed:
                            tasks = session_data.discovery_session.schema.task_curriculum.tasks
                            simple_message = f"I've designed a learning path with {len(tasks)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."

                            await safe_send({
                                "type": "task_curriculum_proposed",
                                "content": simple_message,
                                "curriculum": {
                                    "tasks": [
                                        {
                                            "id": task.id,
                                            "topic": task.topic,
                                            "justification": task.justification,
                                            "prerequisites": task.prerequisites,
                                            "status": task.status
                                        }
                                        for task in tasks
                                    ]
                                },
                                "tasks": [
                                    {
                                        "id": task.id,
                                        "topic": task.topic,
                                        "justification": task.justification,
                                        "prerequisites": task.prerequisites,
                                        "status": task.status
                                    }
                                    for task in tasks
                                ],
                                "message": simple_message
                            })
                        else:
                            await safe_send({
                                "type": "message",
                                "content": result.get("message", "Learning path generation in progress"),
                                "role": "assistant"
                            })

                        _maybe_checkpoint()
                        continue

                    if user_message == "__ACCEPT_CURRICULUM__":
                        await safe_send({"type": "status", "status": ""})
                        result = session_data.discovery_session.accept_proposed_curriculum()

                        if not result.get("success"):
                            await safe_send({
                                "type": "error",
                                "message": result.get("message", "Failed to accept curriculum")
                            })
                            continue

                        try:
                            session_info = _db.get_session_by_id(session_id)
                            goal_id = None

                            if session_info and session_info.get("goal_id"):
                                goal_id = session_info["goal_id"]
                            elif session_info and session_data.discovery_session.schema.interview_state.user_goal:
                                user_id = session_info.get("user_id")
                                goal_text = session_data.discovery_session.schema.interview_state.user_goal
                                if user_id:
                                    goals = _db.get_user_goals(user_id)
                                    matching_goal = next((g for g in goals if g["goal_text"] == goal_text), None)
                                    if matching_goal:
                                        goal_id = matching_goal["id"]
                                        print(f"[Curriculum] Found goal by text: {goal_id}")

                            if goal_id:
                                tasks = result.get("tasks", [])
                                _db.set_goal_teaching_candidates(goal_id, tasks)
                                print(f"[Curriculum] Saved {len(tasks)} tasks to goal {goal_id}")
                            else:
                                print(f"[Curriculum] WARNING: Could not find goal_id to save tasks.")
                        except Exception as e:
                            print(f"[Curriculum] Failed to save tasks to DB: {e}")
                            import traceback
                            traceback.print_exc()

                        tasks = result.get("tasks", [])
                        first_task = tasks[0] if tasks else None

                        await safe_send({
                            "type": "task_curriculum_accepted",
                            "tasks": tasks,
                            "first_task": first_task,
                            "content": f"Great! Let's start with: **{first_task['topic']}**" if first_task else "Curriculum accepted!",
                            "message": result.get("message", "Curriculum accepted")
                        })
                        _maybe_checkpoint()
                        continue

                    # Process regular message with streaming
                    import queue
                    event_queue = queue.Queue()

                    def _run_event_generator():
                        """Run the blocking event generator in a thread, pushing events to queue."""
                        try:
                            for event in session_data.discovery_session.process_user_message_events(
                                user_message, skip_history=is_onboarding_message
                            ):
                                event_queue.put(event)
                        except Exception as e:
                            event_queue.put({"type": "error", "message": str(e)})
                        finally:
                            event_queue.put(None)  # Sentinel: generator done

                    loop = asyncio.get_event_loop()
                    fut = loop.run_in_executor(None, _run_event_generator)

                    full_response = ""
                    wants_audio = data.get("audio_mode", False) or data.get("audio", False)

                    while True:
                        # Poll queue, yielding to event loop between checks
                        try:
                            event = event_queue.get_nowait()
                        except queue.Empty:
                            await asyncio.sleep(0.02)
                            continue

                        if event is None:
                            break  # Generator finished

                        etype = event.get("type")

                        if etype == "stream_start":
                            await safe_send({"type": "status", "status": ""})
                            await safe_send({"type": "stream_start"})

                        elif etype == "stream_chunk":
                            full_response += event["content"]
                            await safe_send({"type": "stream_chunk", "content": event["content"]})

                        elif etype == "stream_end":
                            full_response = event["content"]
                            # Generate audio if requested
                            audio_url = None
                            if wants_audio and full_response.strip() and _audio_service:
                                try:
                                    audio_path = await asyncio.wait_for(
                                        loop.run_in_executor(None, _audio_service.text_to_speech, full_response),
                                        timeout=5.0
                                    )
                                    audio_url = f"/audio/{audio_path.name}"
                                except Exception:
                                    audio_url = None

                            await safe_send({"type": "stream_end", "content": full_response, "audio_url": audio_url})
                            _maybe_checkpoint()

                        elif etype == "complete":
                            full_response = event["content"]
                            audio_url = None
                            if wants_audio and full_response.strip() and _audio_service:
                                try:
                                    audio_path = await asyncio.wait_for(
                                        loop.run_in_executor(None, _audio_service.text_to_speech, full_response),
                                        timeout=5.0
                                    )
                                    audio_url = f"/audio/{audio_path.name}"
                                except Exception:
                                    audio_url = None

                            await safe_send({"type": "status", "status": ""})
                            await safe_send({"type": "message", "content": full_response, "audio_url": audio_url})
                            _maybe_checkpoint()

                        elif etype == "goal_proposed":
                            proposed_goal = event["goal"]
                            goal_message = f"Based on our conversation, here's a learning goal that might resonate: **{proposed_goal}**"
                            audio_url = None
                            if wants_audio and _audio_service:
                                try:
                                    audio_path = await asyncio.wait_for(
                                        loop.run_in_executor(None, _audio_service.text_to_speech, goal_message),
                                        timeout=5.0
                                    )
                                    audio_url = f"/audio/{audio_path.name}"
                                except Exception:
                                    audio_url = None
                            await safe_send({"type": "status", "status": ""})
                            await safe_send({
                                "type": "goal_proposed",
                                "goal": proposed_goal,
                                "content": goal_message,
                                "audio_url": audio_url,
                                "message": f"**Goal identified:** {proposed_goal}"
                            })
                            _maybe_checkpoint()

                        elif etype == "curriculum_proposed":
                            curriculum_response = event.get("response", {})
                            tasks_data = curriculum_response.get("tasks", [])
                            print(f"[Backend] Curriculum proposal: {len(tasks_data)} tasks found")
                            await safe_send({"type": "status", "status": ""})
                            simple_message = f"I've designed a learning path with {len(tasks_data)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."

                            # Build curriculum from schema (already saved by orchestrator)
                            schema_tasks = session_data.discovery_session.schema.task_curriculum.tasks
                            curriculum = {
                                "tasks": [
                                    {
                                        "id": task.id,
                                        "topic": task.topic,
                                        "justification": task.justification,
                                        "prerequisites": task.prerequisites,
                                        "status": task.status
                                    }
                                    for task in schema_tasks
                                ]
                            }
                            await safe_send({
                                "type": "task_curriculum_proposed",
                                "curriculum": curriculum,
                                "content": simple_message,
                                "audio_url": None,
                                "message": simple_message
                            })
                            _maybe_checkpoint()

                        elif etype == "empty":
                            await safe_send({"type": "status", "status": ""})
                            _maybe_checkpoint()

                        elif etype == "error":
                            await safe_send({"type": "error", "message": event.get("message", "Processing error")})

                    # Wait for the thread to finish
                    await fut

                    # Push updated schema to frontend for real-time profile/teaching candidate updates
                    try:
                        schema = session_data.discovery_session.get_schema()
                        await safe_send({"type": "schema_update", "schema": schema})
                    except Exception as schema_err:
                        print(f"[WS] Schema push error: {schema_err}")

                except Exception as e:
                    print(f"[WS ERROR] Command processing failed: {e}")
                    import traceback
                    traceback.print_exc()
                    await safe_send({
                        "type": "error",
                        "message": f"An error occurred processing your message. Please try again."
                    })
                    continue

        except WebSocketDisconnect:
            print(f"WebSocket disconnected for session {session_id}")
        except Exception as e:
            print(f"Error in discovery websocket: {e}")
            import traceback
            traceback.print_exc()

            error_message = str(e)
            if "rate limit" in error_message.lower() or "429" in error_message or "token" in error_message.lower() and "limit" in error_message.lower():
                friendly_message = "API rate limit reached. The service has hit its daily token quota. Please try again later or contact support."
            else:
                friendly_message = f"An error occurred: {error_message}"

            await safe_send({"type": "error", "message": friendly_message})

            try:
                if not _ws_closed:
                    await websocket.close()
            except Exception as e:
                print(f"[WebSocket] Error closing connection: {e}")

    return discovery_websocket


@router.get("/discovery/{session_id}/schema")
async def get_discovery_schema(session_id: str):
    """Get current discovery schema for debugging."""
    session_data = await _session_manager.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    schema = session_data.discovery_session.get_schema()
    return schema
