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

                should_propose_curriculum = False
                try:
                    schema = session_data.discovery_session.schema
                    assessment_conf = schema.prior_knowledge_assessment.confidence
                    turns = schema.interview_state.turns_elapsed + 1
                    has_candidates = len(schema.teaching_candidates) > 0
                    already_proposed = schema.task_curriculum.proposed

                    should_propose_curriculum = (
                        not already_proposed and
                        has_candidates and
                        (assessment_conf >= 0.5 or turns >= 8)
                    )
                except:
                    pass

                status_message = "Proposing curriculum..." if should_propose_curriculum else "Analyzing your response..."
                await websocket.send_json({
                    "type": "status",
                    "status": status_message
                })

                try:
                    is_explicit_command = user_message.startswith("__") and user_message.endswith("__")

                    if not is_explicit_command:
                        lower_msg = user_message.lower().strip()

                        has_pending_goal = session_data.discovery_session.schema.interview_state.proposed_goal is not None

                        has_pending_curriculum = (
                            session_data.discovery_session.schema.task_curriculum.proposed and
                            not session_data.discovery_session.schema.task_curriculum.accepted and
                            len(session_data.discovery_session.schema.task_curriculum.tasks) > 0
                        )

                        has_pending_teaching = False
                        try:
                            interview_state = session_data.discovery_session.schema.interview_state
                            if hasattr(interview_state, 'proposed_teaching_ids') and interview_state.proposed_teaching_ids:
                                has_pending_teaching = (
                                    len(interview_state.proposed_teaching_ids) > 0 and
                                    (not hasattr(interview_state, 'batch_proposal_pending') or interview_state.batch_proposal_pending == False)
                                )
                        except (AttributeError, TypeError):
                            has_pending_teaching = False

                        accept_phrases = ['yes', 'yeah', 'yep', 'sounds good', 'sounds great', 'accept', 'let\'s do it',
                                         'perfect', 'that works', 'i like it', 'go for it', 'absolutely', 'sure', 'ok', 'okay', 'i accept']
                        reject_phrases = ['no', 'nope', 'not quite', 'not really', 'something else', 'different',
                                         'reject', 'pass', 'skip', 'change', 'try again']

                        is_accept = any(phrase in lower_msg for phrase in accept_phrases) and len(lower_msg) < 50
                        is_reject = any(phrase in lower_msg for phrase in reject_phrases) and len(lower_msg) < 50

                        if has_pending_goal and is_accept:
                            print(f"[Voice] Detected goal acceptance: '{user_message}'")
                            user_message = "__ACCEPT_GOAL__"
                        elif has_pending_goal and is_reject:
                            print(f"[Voice] Detected goal rejection: '{user_message}'")
                            user_message = "__REJECT_GOAL__"
                        elif has_pending_curriculum and is_accept:
                            print(f"[Voice] Detected curriculum acceptance: '{user_message}'")
                            user_message = "__ACCEPT_CURRICULUM__"
                        elif has_pending_curriculum and is_reject:
                            print(f"[Voice] Detected curriculum rejection: '{user_message}'")
                            user_message = "__REJECT_CURRICULUM__"
                        elif has_pending_teaching and is_accept:
                            print(f"[Voice] Detected teaching acceptance: '{user_message}'")
                            user_message = "__ACCEPT_TEACHING__"
                        elif has_pending_teaching and is_reject:
                            print(f"[Voice] Detected teaching rejection: '{user_message}'")
                            user_message = "__REJECT_TEACHING__"

                    is_onboarding_message = False
                    if user_message.startswith("__ONBOARDING__"):
                        background_info = user_message.replace("__ONBOARDING__", "", 1)
                        user_message = background_info
                        is_onboarding_message = True
                        print(f"[WebSocket] Onboarding message detected - will use for context but not add to visible history")

                    # Handle special commands
                    if user_message == "__ACCEPT_GOAL__":
                        await websocket.send_json({"type": "status", "status": ""})
                        result = session_data.discovery_session.accept_proposed_goal()

                        if "error" in result:
                            await websocket.send_json({"type": "error", "message": result["error"]})
                            continue

                        if "error" in result or not result.get("success"):
                            await websocket.send_json({
                                "type": "error",
                                "message": result.get("error") or result.get("message", "Failed to accept goal")
                            })
                            continue

                        await websocket.send_json({
                            "type": "create_goal_panel",
                            "goal": result.get("goal", ""),
                            "goal_id": result.get("goal_id", 0),
                            "message": result.get("message", "Goal accepted")
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__REJECT_GOAL__":
                        await websocket.send_json({"type": "status", "status": ""})
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(
                            None,
                            session_data.discovery_session.reject_proposed_goal
                        )
                        await websocket.send_json({
                            "type": "message",
                            "content": response,
                            "audio_url": None
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__ACCEPT_TEACHING__":
                        await websocket.send_json({"type": "status", "status": ""})
                        result = session_data.discovery_session.accept_proposed_teaching()

                        if not result.get("success"):
                            await websocket.send_json({
                                "type": "error",
                                "message": result.get("message", "Failed to accept teaching candidate")
                            })
                            continue

                        try:
                            session_info = _db.get_session_by_id(session_id)
                            if session_info and session_info.get("goal_id"):
                                _db.update_goal_teaching_candidate(
                                    session_info["goal_id"],
                                    result.get("candidate", {})
                                )
                                print(f"[Teaching] Saved teaching candidate to goal {session_info['goal_id']}")
                        except Exception as e:
                            print(f"[Teaching] Failed to save teaching candidate to DB: {e}")

                        await websocket.send_json({
                            "type": "create_teaching_panel",
                            "candidate": result.get("candidate", {}),
                            "message": result.get("message", "Teaching candidate accepted")
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__REJECT_TEACHING__":
                        await websocket.send_json({"type": "status", "status": ""})
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(
                            None,
                            session_data.discovery_session.reject_proposed_teaching
                        )
                        await websocket.send_json({
                            "type": "message",
                            "content": response,
                            "audio_url": None
                        })
                        _maybe_checkpoint()
                        continue

                    if user_message == "__GENERATE_LEARNING_PATH__":
                        await websocket.send_json({"type": "status", "status": ""})
                        result = session_data.discovery_session.generate_learning_path()

                        if not result.get("success"):
                            await websocket.send_json({
                                "type": "error",
                                "message": result.get("message", "Failed to generate learning path")
                            })
                            continue

                        if session_data.discovery_session.schema.task_curriculum.proposed:
                            tasks = session_data.discovery_session.schema.task_curriculum.tasks
                            simple_message = f"I've designed a learning path with {len(tasks)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."

                            await websocket.send_json({
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
                            await websocket.send_json({
                                "type": "message",
                                "content": result.get("message", "Learning path generation in progress"),
                                "role": "assistant"
                            })

                        _maybe_checkpoint()
                        continue

                    if user_message == "__ACCEPT_CURRICULUM__":
                        await websocket.send_json({"type": "status", "status": ""})
                        result = session_data.discovery_session.accept_proposed_curriculum()

                        if not result.get("success"):
                            await websocket.send_json({
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

                        await websocket.send_json({
                            "type": "task_curriculum_accepted",
                            "tasks": tasks,
                            "first_task": first_task,
                            "content": f"Great! Let's start with: **{first_task['topic']}**" if first_task else "Curriculum accepted!",
                            "message": result.get("message", "Curriculum accepted")
                        })
                        _maybe_checkpoint()
                        continue

                    # Process regular message
                    loop = asyncio.get_event_loop()

                    def process_with_flag():
                        return session_data.discovery_session.process_user_message(
                            user_message,
                            skip_history=is_onboarding_message
                        )

                    response = await loop.run_in_executor(None, process_with_flag)

                    if not response or response.strip() == "":
                        await websocket.send_json({"type": "status", "status": ""})
                        _maybe_checkpoint()
                        continue

                    if response.startswith("__GOAL_PROPOSED__:"):
                        proposed_goal = response.split(":", 1)[1]
                        goal_message = f"I think I've identified a learning goal for you: {proposed_goal}. Does this sound right?"

                        await websocket.send_json({"type": "status", "status": ""})
                        await websocket.send_json({
                            "type": "goal_proposed",
                            "goal": proposed_goal,
                            "content": goal_message,
                            "audio_url": None,
                            "message": f"**Goal identified:** {proposed_goal}"
                        })
                        _maybe_checkpoint()
                        continue

                    if response.startswith("__TASK_CURRICULUM_PROPOSED__:"):
                        import json as json_module
                        curriculum_json = response.split(":", 1)[1]
                        curriculum = json_module.loads(curriculum_json)

                        tasks = curriculum.get('tasks', [])
                        print(f"[Backend] Curriculum proposal: {len(tasks)} tasks found")

                        await websocket.send_json({"type": "status", "status": ""})
                        simple_message = f"I've designed a learning path with {len(tasks)} tasks to help you achieve your goal. Review it below and let me know if you'd like to adjust anything."
                        await websocket.send_json({
                            "type": "task_curriculum_proposed",
                            "curriculum": curriculum,
                            "content": simple_message,
                            "audio_url": None,
                            "message": simple_message
                        })
                        _maybe_checkpoint()
                        continue

                    if response.startswith("__TEACHING_PROPOSED__:"):
                        import json as json_module
                        candidate_json = response.split(":", 1)[1]
                        candidate = json_module.loads(candidate_json)
                        teaching_message = f"I think I found a great starting point: {candidate['topic']}. Want to explore this?"

                        await websocket.send_json({"type": "status", "status": ""})
                        await websocket.send_json({
                            "type": "teaching_proposed",
                            "candidate": candidate,
                            "content": teaching_message,
                            "audio_url": None,
                            "message": f"I think I found a great starting point: **{candidate['topic']}**"
                        })
                        _maybe_checkpoint()
                        continue

                    audio_url = None
                    wants_audio = data.get("audio_mode", False) or data.get("audio", False)

                    if wants_audio and response and response.strip() and _audio_service:
                        try:
                            loop = asyncio.get_event_loop()
                            audio_path = await asyncio.wait_for(
                                loop.run_in_executor(
                                    None,
                                    _audio_service.text_to_speech,
                                    response
                                ),
                                timeout=5.0
                            )
                            audio_url = f"/audio/{audio_path.name}"
                        except asyncio.TimeoutError:
                            print(f"[Audio] TTS generation timed out after 5s - sending response without audio")
                            audio_url = None
                        except Exception as e:
                            print(f"[Audio] TTS generation failed: {e}")
                            audio_url = None

                    if session_data.discovery_session.is_complete():
                        await websocket.send_json({"type": "status", "status": ""})
                        final_topic = session_data.discovery_session.get_final_topic()

                        if not final_topic or not hasattr(final_topic, 'topic'):
                            print(f"[WS ERROR] Invalid final_topic returned from get_final_topic()")
                            await websocket.send_json({
                                "type": "error",
                                "message": "Failed to extract topic information"
                            })
                            continue

                        await _session_manager.save_final_topic(session_id, final_topic)

                        await websocket.send_json({
                            "type": "topic_found",
                            "content": response,
                            "audio_url": audio_url,
                            "topic": {
                                "topic": final_topic.topic,
                                "user_confusion": final_topic.user_confusion,
                                "stakes": final_topic.stakes,
                                "learning_hook": final_topic.learning_hook,
                                "suggested_angles": final_topic.suggested_angles,
                                "scores": final_topic.scores.to_dict() if final_topic.scores else {}
                            }
                        })
                        _maybe_checkpoint()
                    else:
                        await websocket.send_json({"type": "status", "status": ""})
                        await websocket.send_json({
                            "type": "message",
                            "content": response,
                            "audio_url": audio_url
                        })
                        _maybe_checkpoint()

                except Exception as e:
                    print(f"[WS ERROR] Command processing failed: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_json({
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

            try:
                await websocket.send_json({"type": "error", "message": friendly_message})
            except Exception as e:
                print(f"[WebSocket] Error sending error message: {e}")

            try:
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
