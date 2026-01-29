"""Document and context endpoints and WebSocket handlers."""
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api", tags=["documents"])

# Database and services will be injected
_db = None
_document_suggestion_service = None
_suggestion_router = None
active_document_connections: dict = {}


def init_router(db, document_suggestion_service=None, suggestion_router=None):
    """Initialize router with database and services."""
    global _db, _document_suggestion_service, _suggestion_router
    _db = db
    _document_suggestion_service = document_suggestion_service
    _suggestion_router = suggestion_router


class ContextTextRequest(BaseModel):
    goal_id: int
    user_id: str
    text_content: str
    content_type: str = "text"


class ContextResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    content_type: str
    text_content: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    token_count: int
    is_active: bool
    created_at: Optional[str] = None


class DocumentCreateRequest(BaseModel):
    goal_id: int
    user_id: str
    title: str = "Untitled"
    document_type: str = "notes"
    content: Optional[dict] = None
    plain_text: Optional[str] = None


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    document_type: Optional[str] = None
    content: Optional[dict] = None
    plain_text: Optional[str] = None


class DocumentConfigRequest(BaseModel):
    formatting: bool = True
    content: bool = True
    tasks: bool = False


class DocumentResponse(BaseModel):
    id: int
    goal_id: int
    user_id: str
    title: str
    document_type: str
    content: Optional[dict] = None
    plain_text: Optional[str] = None
    suggestion_config: dict
    version: int
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Context Tab Endpoints

@router.post("/goal/{goal_id}/context", response_model=ContextResponse)
async def add_context(goal_id: int, request: ContextTextRequest):
    """Add text context to a goal."""
    try:
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        context = _db.create_goal_context(
            goal_id=request.goal_id,
            user_id=request.user_id,
            content_type=request.content_type,
            text_content=request.text_content,
            processed_content=request.text_content,
            token_count=len(request.text_content.split())
        )
        return ContextResponse(**context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goal/{goal_id}/contexts", response_model=List[ContextResponse])
async def get_contexts(goal_id: int):
    """Get all context items for a goal."""
    try:
        contexts = _db.get_goal_contexts(goal_id)
        return [ContextResponse(**c) for c in contexts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/goal/{goal_id}/context/{context_id}", response_model=ContextResponse)
async def update_context(goal_id: int, context_id: int, updates: dict):
    """Update a context item."""
    try:
        context = _db.update_goal_context(context_id, updates)
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")
        return ContextResponse(**context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/goal/{goal_id}/context/{context_id}")
async def delete_context(goal_id: int, context_id: int):
    """Delete a context item (soft delete)."""
    try:
        success = _db.delete_goal_context(context_id, soft_delete=True)
        if not success:
            raise HTTPException(status_code=404, detail="Context not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Document Tab Endpoints

@router.post("/goal/{goal_id}/document", response_model=DocumentResponse)
async def create_document(goal_id: int, request: DocumentCreateRequest):
    """Create a new document for a goal."""
    try:
        if goal_id != request.goal_id:
            raise HTTPException(status_code=400, detail="Goal ID mismatch")

        document = _db.create_goal_document(
            goal_id=request.goal_id,
            user_id=request.user_id,
            title=request.title,
            document_type=request.document_type,
            content=request.content,
            plain_text=request.plain_text
        )
        return DocumentResponse(**document)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/goal/{goal_id}/documents", response_model=List[DocumentResponse])
async def get_documents(goal_id: int):
    """Get all documents for a goal."""
    try:
        documents = _db.get_goal_documents(goal_id)
        return [DocumentResponse(**d) for d in documents]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/document/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int):
    """Get a specific document."""
    try:
        document = _db.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/document/{document_id}", response_model=DocumentResponse)
async def update_document(document_id: int, request: DocumentUpdateRequest):
    """Update a document."""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        document = _db.update_document(document_id, updates)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/document/{document_id}/config", response_model=DocumentResponse)
async def update_document_config(document_id: int, request: DocumentConfigRequest):
    """Update document suggestion preferences."""
    try:
        config = request.model_dump()
        document = _db.update_document_suggestion_config(document_id, config)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/document/{document_id}/expand-suggestion")
async def expand_suggestion(document_id: int, request: dict):
    """Expand a document suggestion with implementation ideas and questions."""
    try:
        suggestion = request.get("suggestion", {})
        document_content = request.get("document_content", "")
        goal_id = request.get("goal_id")

        if not suggestion or not suggestion.get("text"):
            raise HTTPException(status_code=400, detail="Suggestion text required")

        goal = _db.get_goal_by_id(goal_id) if goal_id else None
        goal_text = goal["goal_text"] if goal else ""

        from src.llm_client import LLMClient
        from src.config import get_model_name

        llm = LLMClient()
        model = get_model_name("ranker", default="openai:gpt-4o-mini")

        prompt = f"""You are helping someone improve their document. They received this suggestion:

SUGGESTION TYPE: {suggestion.get('suggestion_type', 'general')}
SUGGESTION: {suggestion.get('text', '')}
LOCATION: {suggestion.get('location', 'N/A')}

CONTEXT:
- Goal: "{goal_text}"
- Document content (excerpt): {document_content[:1000]}

Generate a concise, direct message that includes:
1. Brief explanation of the suggestion (1-2 sentences)
2. 2-3 specific, actionable implementation ideas
3. 1-2 focused questions to guide implementation

Write directly and concisely. Skip greetings and filler phrases like "Hey there!" or "I noticed". Get straight to the point. Return just the message text, no JSON or formatting markers."""

        expanded_message = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.7,
            max_tokens=500
        )

        return {
            "expanded_message": expanded_message.strip(),
            "suggestion": suggestion
        }
    except Exception as e:
        print(f"[ExpandSuggestion] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/goal/{goal_id}/panels/init")
async def initialize_goal_panels(goal_id: int, user_id: str = Query(None)):
    """Initialize default chat channels for a goal's panel system."""
    try:
        if not user_id:
            goal = _db.get_goal_by_id(goal_id)
            if goal:
                user_id = goal.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        result = _db.initialize_goal_panels(goal_id, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_document_websocket_handler():
    """Return the WebSocket handler for document sessions."""

    async def document_websocket(websocket: WebSocket, document_id: int):
        """WebSocket for real-time document sync and AI suggestions."""
        await websocket.accept()

        if document_id not in active_document_connections:
            active_document_connections[document_id] = []
        active_document_connections[document_id].append(websocket)

        try:
            document = _db.get_document_by_id(document_id)
            if not document:
                await websocket.send_json({"type": "error", "message": "Document not found"})
                await websocket.close()
                return

            goal_id = document["goal_id"]

            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "update":
                    content = data.get("content", {})
                    plain_text = data.get("plain_text", "")

                    updates = {}
                    if plain_text is not None and plain_text != "":
                        updates["plain_text"] = plain_text
                    if content is not None and content != {}:
                        updates["content"] = content

                    updated = None
                    if updates:
                        updated = _db.update_document(document_id, updates)

                    await websocket.send_json({
                        "type": "sync_ack",
                        "version": updated["version"] if updated else 0
                    })

                    async def send_suggestions(suggestions):
                        try:
                            from dataclasses import asdict
                            suggestions_dict = [asdict(s) for s in suggestions]
                            await websocket.send_json({
                                "type": "suggestions",
                                "suggestions": suggestions_dict
                            })

                            if _suggestion_router:
                                await _suggestion_router.route_document_suggestions(
                                    goal_id=goal_id,
                                    document_id=document_id,
                                    suggestions=suggestions_dict
                                )
                        except Exception as e:
                            print(f"[DocumentWS] Error sending suggestions: {e}")

                    goal = _db.get_goal_by_id(goal_id)
                    goal_context = {"goal_text": goal["goal_text"]} if goal else {}
                    config = document.get("suggestion_config", {})

                    from backend.services.document_suggestion import SuggestionConfig as DocSuggestionConfig
                    suggestion_config = DocSuggestionConfig(
                        formatting=config.get("formatting", True),
                        content=config.get("content", True),
                        tasks=config.get("tasks", False)
                    )

                    if _document_suggestion_service:
                        _document_suggestion_service.schedule_suggestions(
                            document_id=document_id,
                            plain_text=plain_text,
                            goal_context=goal_context,
                            config=suggestion_config,
                            callback=send_suggestions
                        )

                elif msg_type == "request_suggestion":
                    print(f"[DocumentWS] Requesting suggestions for document {document_id}")
                    selection = data.get("selection", "")
                    plain_text = selection or document.get("plain_text", "")

                    print(f"[DocumentWS] Document plain_text length: {len(plain_text) if plain_text else 0}")

                    if not plain_text or len(plain_text.strip()) < 20:
                        error_msg = "Document needs at least 20 characters for AI analysis"
                        print(f"[DocumentWS] {error_msg}")
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })
                        return

                    goal = _db.get_goal_by_id(goal_id)
                    goal_context = {"goal_text": goal["goal_text"]} if goal else {}
                    config = document.get("suggestion_config", {})

                    from backend.services.document_suggestion import SuggestionConfig as DocSuggestionConfig
                    suggestion_config = DocSuggestionConfig(
                        formatting=config.get("formatting", True),
                        content=config.get("content", True),
                        tasks=config.get("tasks", False)
                    )

                    try:
                        print(f"[DocumentWS] Generating suggestions for {len(plain_text)} characters...")

                        if _document_suggestion_service:
                            suggestions = await _document_suggestion_service.generate_suggestions(
                                document_id=document_id,
                                plain_text=plain_text,
                                goal_context=goal_context,
                                config=suggestion_config
                            )

                            print(f"[DocumentWS] Generated {len(suggestions)} suggestions")
                            from dataclasses import asdict
                            suggestions_dict = [asdict(s) for s in suggestions]

                            await websocket.send_json({
                                "type": "suggestions",
                                "suggestions": suggestions_dict
                            })
                            print(f"[DocumentWS] Sent suggestions message to client")
                    except Exception as e:
                        print(f"[DocumentWS] Error generating suggestions: {e}")
                        import traceback
                        traceback.print_exc()
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Failed to generate suggestions: {str(e)}"
                        })

                elif msg_type == "update_config":
                    config = data.get("config", {})
                    _db.update_document_suggestion_config(document_id, config)
                    await websocket.send_json({"type": "config_updated", "config": config})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[DocumentWS] Error: {e}")
        finally:
            if document_id in active_document_connections:
                active_document_connections[document_id] = [
                    ws for ws in active_document_connections[document_id] if ws != websocket
                ]

    return document_websocket
