"""Teaching curriculum endpoints and WebSocket handler."""
import os
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api", tags=["teaching"])

# Database and services will be injected
_db = None
_audio_service = None
teaching_sessions: dict = {}


def init_router(db, audio_service=None):
    """Initialize router with database instance."""
    global _db, _audio_service
    _db = db
    _audio_service = audio_service


class TeachingStartRequest(BaseModel):
    user_id: str
    goal_id: int
    goal_text: str
    teaching_candidate_id: int
    topic: str
    identified_gap: Optional[str] = ""
    focus_question: Optional[str] = ""
    goal_conversation_history: list = []
    user_background: str = ""
    current_model_summary: Optional[str] = None
    stakes_summary: Optional[str] = None
    llm_config: Optional[dict] = None


class TeachingStartResponse(BaseModel):
    session_id: str
    opening_message: str
    conversation_history: list = []
    is_resumed: bool = False
    curriculum_plan: Optional[dict] = None
    phase: Optional[str] = None
    message_type: Optional[str] = None


class TeachingChatRequest(BaseModel):
    session_id: str
    message: str


class TeachingChatResponse(BaseModel):
    response: str
    curriculum_progress: Optional[dict] = None
    narrative_summary: Optional[str] = None


@router.post("/teaching/start", response_model=TeachingStartResponse)
async def start_teaching(request: TeachingStartRequest):
    """Initialize or resume a teaching session with curriculum-based learning."""
    try:
        from src.agents.teaching_orchestrator import TeachingOrchestrator

        existing_candidates = _db.get_teaching_candidates_for_goal(request.goal_id)
        existing_candidates = [c for c in existing_candidates if c.get("id") != request.teaching_candidate_id]
        print(f"[Teaching] Found {len(existing_candidates)} existing teaching candidates for goal {request.goal_id}")

        existing = _db.get_session_for_teaching(request.goal_id, request.teaching_candidate_id)

        if existing and existing.get("session_id"):
            session_id = existing["session_id"]
            conversation_history = existing.get("conversation_history", [])
            schema_state = existing.get("schema_state")

            print(f"[Teaching] Resuming session: {session_id[:8]}... ({len(conversation_history)} messages)")

            teaching_candidate = {
                "topic": request.topic,
                "focus_question": request.focus_question,
                "identified_gap": request.identified_gap,
                "current_model_summary": request.current_model_summary,
                "stakes_summary": request.stakes_summary
            }

            db_path = os.getenv("DATABASE_PATH", "data/liminal.db")

            orchestrator = TeachingOrchestrator(
                user_id=request.user_id,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id,
                teaching_candidate=teaching_candidate,
                goal_text=request.goal_text,
                user_background=request.user_background,
                goal_conversation_history=request.goal_conversation_history,
                existing_teaching_candidates=existing_candidates,
                db_path=db_path,
                model_config=request.llm_config,
                session_id=session_id,
                conversation_history=conversation_history,
                schema_state=schema_state
            )

            teaching_sessions[session_id] = orchestrator

            return TeachingStartResponse(
                session_id=session_id,
                opening_message="",
                conversation_history=conversation_history,
                is_resumed=True,
                curriculum_plan=orchestrator.schema.curriculum_plan.model_dump() if orchestrator.schema.curriculum_plan else None
            )

        teaching_candidate = {
            "topic": request.topic,
            "focus_question": request.focus_question,
            "identified_gap": request.identified_gap,
            "current_model_summary": request.current_model_summary,
            "stakes_summary": request.stakes_summary
        }

        db_path = os.getenv("DATABASE_PATH", "data/liminal.db")

        orchestrator = TeachingOrchestrator(
            user_id=request.user_id,
            goal_id=request.goal_id,
            teaching_candidate_id=request.teaching_candidate_id,
            teaching_candidate=teaching_candidate,
            goal_text=request.goal_text,
            user_background=request.user_background,
            goal_conversation_history=request.goal_conversation_history,
            existing_teaching_candidates=existing_candidates,
            db_path=db_path,
            model_config=request.llm_config
        )

        session_id = orchestrator.session_id

        _db.create_session_with_type(
            session_id,
            request.user_id,
            'teaching',
            request.goal_id,
            request.teaching_candidate_id
        )

        start_result = orchestrator.start()

        teaching_sessions[session_id] = orchestrator

        print(f"[Teaching] Created new session: {session_id[:8]}... for topic: {request.topic} (phase: {start_result.get('phase', 'unknown')})")

        return TeachingStartResponse(
            session_id=session_id,
            opening_message=start_result.get("message", ""),
            conversation_history=orchestrator.conversation_history,
            is_resumed=False,
            curriculum_plan=orchestrator.schema.curriculum_plan.model_dump() if orchestrator.schema.curriculum_plan.steps else None,
            phase=start_result.get("phase"),
            message_type=start_result.get("type")
        )

    except Exception as e:
        print(f"[Teaching Start] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teaching/{session_id}/state")
async def get_teaching_state(session_id: str):
    """Get current teaching state for ProfilePanel display."""
    try:
        if session_id in teaching_sessions:
            orchestrator = teaching_sessions[session_id]
            return orchestrator.get_schema()

        session_data = _db.get_session_by_id(session_id)
        if session_data and session_data.get("schema_state"):
            return session_data["schema_state"]

        raise HTTPException(status_code=404, detail="Teaching session not found")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Teaching State] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teaching/chat", response_model=TeachingChatResponse)
async def teaching_chat(request: TeachingChatRequest):
    """Process a message in a teaching session via REST (alternative to WebSocket)."""
    try:
        orchestrator = teaching_sessions.get(request.session_id)

        if not orchestrator:
            raise HTTPException(status_code=404, detail="Teaching session not found. Use /api/teaching/start first.")

        response = orchestrator.process_user_message(request.message)

        schema = orchestrator.get_schema()

        return TeachingChatResponse(
            response=response,
            curriculum_progress={
                "current_step": schema.get("current_step_index", 0),
                "total_steps": len(schema.get("curriculum_plan", {}).get("steps", [])),
                "completed_steps": len(schema.get("curriculum_plan", {}).get("completed_step_ids", []))
            },
            narrative_summary=schema.get("narrative_summary")
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Teaching Chat] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def get_teaching_websocket_handler():
    """Return the WebSocket handler for teaching sessions."""

    async def teaching_websocket(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for teaching curriculum conversation."""
        await websocket.accept()

        orchestrator = teaching_sessions.get(session_id)
        session_info = None

        if not orchestrator:
            session_data = _db.get_session_by_id(session_id)
            if session_data and session_data.get("schema_state"):
                await websocket.send_json({
                    "type": "error",
                    "message": "Teaching session expired. Please restart from the teaching panel."
                })
                await websocket.close()
                return
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Teaching session not found"
                })
                await websocket.close()
                return

        try:
            try:
                session_info = _db.get_session_by_id(session_id) or {}
            except Exception:
                session_info = {}

            await websocket.send_json({
                "type": "status",
                "status": ""
            })

            def _maybe_checkpoint(teaching_schema: dict):
                """Persist a sparse trajectory checkpoint for this user (best-effort)."""
                try:
                    user_id = (teaching_schema or {}).get("user_id") or getattr(orchestrator, "user_id", None)
                    if not user_id:
                        return
                    _db.maybe_write_trajectory_checkpoint(
                        user_id=user_id,
                        session_id=session_id,
                        session_type=session_info.get("session_type") or "teaching",
                        goal_id=session_info.get("goal_id"),
                        teaching_candidate_id=session_info.get("teaching_candidate_id"),
                        schema_state=teaching_schema,
                        conversation_history=getattr(orchestrator, "conversation_history", None),
                        turn_index=(teaching_schema or {}).get("turns_elapsed"),
                    )
                except Exception as e:
                    print(f"[Trajectory] Teaching checkpoint failed: {e}")

            while True:
                data = await websocket.receive_json()
                user_message = data.get("content", "")
                wants_audio = data.get("audio_mode", False) or data.get("audio", False)

                command = data.get("command")
                if command:
                    user_message = command

                if not user_message:
                    continue

                await websocket.send_json({
                    "type": "status",
                    "status": "Processing..."
                })

                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        orchestrator.process_user_message,
                        user_message
                    )

                    schema = orchestrator.get_schema()

                    message_type = result.get("type", "teaching_message")
                    message_content = result.get("message", "")
                    phase = result.get("phase", "teaching")

                    if orchestrator.is_complete():
                        try:
                            session_info = _db.get_session_by_id(session_id)
                            if session_info and session_info.get("goal_id"):
                                goal_id = session_info["goal_id"]
                                teaching_candidate_id = session_info.get("teaching_candidate_id")

                                if not teaching_candidate_id:
                                    print(f"[Teaching] WARNING: No teaching_candidate_id found in session_info for session {session_id}")
                                    teaching_candidate_id = schema.get("teaching_candidate_id")

                                if teaching_candidate_id:
                                    goal = _db.get_goal_by_id(goal_id)
                                    if goal and goal.get("teaching_candidate"):
                                        teaching_candidates = goal["teaching_candidate"]

                                        if not isinstance(teaching_candidates, list):
                                            teaching_candidates = [teaching_candidates] if teaching_candidates else []

                                        found_current = False
                                        next_available_idx = None

                                        for idx, tc in enumerate(teaching_candidates):
                                            tc_id = tc.get("id") if isinstance(tc, dict) else None
                                            if tc_id is not None:
                                                try:
                                                    if int(tc_id) == int(teaching_candidate_id):
                                                        tc["status"] = "completed"
                                                        found_current = True
                                                        print(f"[Teaching] Marked task {tc_id} ({tc.get('topic', 'unknown')}) as completed")
                                                        if idx + 1 < len(teaching_candidates):
                                                            next_available_idx = idx + 1
                                                        break
                                                except (ValueError, TypeError) as e:
                                                    continue

                                        if next_available_idx is not None:
                                            next_tc = teaching_candidates[next_available_idx]
                                            if isinstance(next_tc, dict):
                                                next_tc["status"] = "available"
                                                print(f"[Teaching] Unlocked next teaching candidate: {next_tc.get('topic', 'unknown')}")

                                        _db.set_goal_teaching_candidates(goal_id, teaching_candidates)
                        except Exception as e:
                            print(f"[Teaching] Failed to update teaching candidate status: {e}")
                            import traceback
                            traceback.print_exc()

                        await websocket.send_json({
                            "type": "teaching_complete",
                            "content": message_content,
                            "message": "You've demonstrated strong understanding of this topic!",
                            "final_markers": schema.get("understanding_markers", [])
                        })
                        _maybe_checkpoint(schema)
                    else:
                        response_data = {
                            "type": message_type,
                            "content": message_content,
                            "phase": phase,
                            "curriculum_progress": result.get("curriculum_progress", {
                                "current_step": schema.get("current_step_index", 0),
                                "total_steps": len(schema.get("curriculum_plan", {}).get("steps", [])),
                                "completed_steps": len(schema.get("curriculum_plan", {}).get("completed_step_ids", []))
                            }),
                            "narrative_summary": schema.get("narrative_summary", ""),
                        }

                        if phase == "teaching":
                            response_data["understanding_markers"] = [
                                {
                                    "id": m.get("id"),
                                    "name": m.get("name"),
                                    "level": m.get("level"),
                                    "evidence": m.get("evidence", [])[-1] if m.get("evidence") else None
                                }
                                for m in schema.get("understanding_markers", [])
                                if m.get("level") != "not_yet"
                            ]

                        if wants_audio and message_content and message_content.strip() and _audio_service:
                            try:
                                loop = asyncio.get_event_loop()
                                audio_path = await asyncio.wait_for(
                                    loop.run_in_executor(
                                        None,
                                        _audio_service.text_to_speech,
                                        message_content
                                    ),
                                    timeout=5.0
                                )
                                response_data["audio_url"] = f"/audio/{audio_path.name}"
                            except asyncio.TimeoutError:
                                print(f"[Audio] TTS generation timed out after 5s - sending response without audio")
                            except Exception as e:
                                print(f"[Audio] TTS generation failed: {e}")

                        await websocket.send_json(response_data)
                        _maybe_checkpoint(schema)

                except Exception as e:
                    print(f"[Teaching WS] Error processing message: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_json({
                        "type": "error",
                        "message": "An error occurred. Please try again."
                    })
                    continue

        except WebSocketDisconnect:
            print(f"[Teaching WS] Disconnected: {session_id[:8]}...")
        except Exception as e:
            print(f"[Teaching WS] Error: {e}")
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
                await websocket.close()
            except:
                pass

    return teaching_websocket
