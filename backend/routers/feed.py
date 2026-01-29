"""Feed content generation endpoints."""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

router = APIRouter(prefix="/api", tags=["feed"])

# Database instance will be injected
_db = None


def init_router(db):
    """Initialize router with database instance."""
    global _db
    _db = db


class FeedRequest(BaseModel):
    user_id: str
    context_type: str  # 'exploration', 'goal', or 'teaching_candidate'
    goal_id: Optional[int] = None
    goal_text: Optional[str] = None
    teaching_candidate_id: Optional[str] = None
    teaching_topic: Optional[str] = None
    user_background: Optional[str] = None
    goals_summary: Optional[str] = None


class FeedItemResponse(BaseModel):
    id: int
    title: str
    content: str
    source_citation: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None  # video, article, paper, blog, course
    thumbnail_url: Optional[str] = None
    embed_url: Optional[str] = None
    relevance_note: Optional[str] = None


class FeedResponse(BaseModel):
    items: List[FeedItemResponse]
    generated: bool


@router.post("/feed", response_model=FeedResponse)
async def get_or_generate_feed(request: FeedRequest):
    """Get feed items for a context, generating if needed."""
    try:
        has_feed = _db.has_feed_items(
            user_id=request.user_id,
            context_type=request.context_type,
            goal_id=request.goal_id,
            teaching_candidate_id=request.teaching_candidate_id
        )

        if has_feed:
            items = _db.get_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
            return FeedResponse(
                items=[FeedItemResponse(**item) for item in items],
                generated=False
            )

        from src.llm_client import LLMClient

        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "feed" / "generate_feed.txt"
        with open(prompt_path) as f:
            prompt_template = f.read()

        context_details = ""
        user_background_for_prompt = request.user_background or "No background provided"

        if request.context_type == "exploration":
            context_details = f"User is exploring potential learning directions.\nCurrent interests/goals: {request.goals_summary or 'Still discovering'}"
        elif request.context_type == "goal":
            context_details = f"User's learning goal: {request.goal_text}"
            user_background_for_prompt = "Focus ONLY on the learning goal specified above. Ignore any general user background that is not directly relevant to this specific goal."
        elif request.context_type == "teaching_candidate":
            context_details = f"Goal: {request.goal_text}\nSpecific topic: {request.teaching_topic}"
            user_background_for_prompt = "Focus ONLY on the specific teaching topic mentioned above. Ignore any general user background that is not directly relevant to this specific topic."

        prompt = prompt_template.format(
            context_type=request.context_type,
            context_details=context_details,
            user_background=user_background_for_prompt,
            num_items=7
        )

        llm = LLMClient()
        response = None
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: llm.chat_with_json(
                        messages=[{"role": "user", "content": prompt}],
                        model="openai:gpt-4o-mini",
                        json_top_level="array",
                        max_retries=3
                    )
                ),
                timeout=300.0
            )
        except asyncio.TimeoutError:
            print(f"[Feed] LLM call timed out after 180s - this is unusual, check API status")
            return FeedResponse(items=[], generated=False)
        except Exception as e:
            print(f"[Feed] Error generating feed: {e}")
            import traceback
            traceback.print_exc()
            return FeedResponse(items=[], generated=False)

        if response is None:
            print(f"[Feed] No response from LLM - returning empty feed")
            return FeedResponse(items=[], generated=False)

        if isinstance(response, list):
            items = response
        elif isinstance(response, dict) and "items" in response:
            items = response["items"]
        else:
            print(f"[Feed] Unexpected response format: {type(response)}")
            items = []

        validated_items = []
        for item in items:
            if isinstance(item, dict) and "title" in item and "content" in item:
                validated_items.append(item)
            else:
                print(f"[Feed] Skipping invalid item: {item}")

        items = validated_items

        if not items:
            print(f"[Feed] No items generated - likely not enough conversation yet")
            return FeedResponse(items=[], generated=False)

        save_successful = False
        if items:
            try:
                _db.save_feed_items(
                    user_id=request.user_id,
                    context_type=request.context_type,
                    items=items,
                    goal_id=request.goal_id,
                    teaching_candidate_id=request.teaching_candidate_id
                )
                save_successful = True
            except Exception as e:
                print(f"[Feed] Failed to save items to database: {e}")
                import traceback
                traceback.print_exc()

        if save_successful:
            saved_items = _db.get_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
            print(f"[Feed] Retrieved {len(saved_items)} saved items from database")
            try:
                response_items = [FeedItemResponse(**item) for item in saved_items]
                return FeedResponse(
                    items=response_items,
                    generated=True
                )
            except Exception as e:
                print(f"[Feed] Error creating FeedItemResponse from saved items: {e}")
                import traceback
                traceback.print_exc()
                return FeedResponse(
                    items=[FeedItemResponse(id=i, **item) for i, item in enumerate(items)],
                    generated=True
                )
        else:
            return FeedResponse(
                items=[FeedItemResponse(id=i, **item) for i, item in enumerate(items)],
                generated=True
            )

    except Exception as e:
        print(f"[Feed] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/feed/{user_id}/{context_type}")
async def clear_feed(user_id: str, context_type: str, goal_id: Optional[int] = None):
    """Clear feed items to force regeneration."""
    try:
        return {"success": True, "message": "Feed will be regenerated on next request"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
