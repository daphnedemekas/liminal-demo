"""Feed content generation endpoints."""
import asyncio
import json
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
    refresh: bool = False  # If true, clear cached feed and re-fetch
    goals_summary: Optional[str] = None
    page: int = 0  # For pagination / load-more


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
    engagement: Optional[int] = None  # likes, points, citations, etc.


class FeedResponse(BaseModel):
    items: List[FeedItemResponse]
    generated: bool


def _interleave_by_type(items: List[dict]) -> List[dict]:
    """Reorder items so no two consecutive items share the same source_type.
    Prioritizes articles/videos/papers over discussions/tweets."""
    if len(items) <= 1:
        return items

    # Priority order: higher = picked first when buckets have equal size
    TYPE_PRIORITY = {
        "article": 6, "paper": 5, "video": 4, "course": 4, "blog": 3,
        "discussion": 2, "tweet": 1, "general": 0,
    }

    # Group by source_type
    from collections import defaultdict, deque
    buckets = defaultdict(deque)
    for item in items:
        buckets[item.get("source_type", "general")].append(item)

    result = []
    last_type = None
    remaining = sum(len(b) for b in buckets.values())

    while remaining > 0:
        # Pick the best bucket: different type from last, then by priority, then by fullness
        best_type = None
        best_score = (-1, -1)
        for t, b in buckets.items():
            if len(b) > 0 and t != last_type:
                score = (TYPE_PRIORITY.get(t, 0), len(b))
                if score > best_score:
                    best_type = t
                    best_score = score

        # If all remaining are the same type, just take from whatever's left
        if best_type is None:
            for t, b in buckets.items():
                if len(b) > 0:
                    best_type = t
                    break

        if best_type is None:
            break

        result.append(buckets[best_type].popleft())
        last_type = best_type
        remaining -= 1

    return result


def _build_context_description(request: FeedRequest) -> str:
    """Build a text description of the learning context for query generation."""
    if request.context_type == "exploration":
        return f"User is exploring learning directions. Interests/goals: {request.goals_summary or 'Still discovering'}. Background: {request.user_background or 'Not provided'}"
    elif request.context_type == "goal":
        return f"Learning goal: {request.goal_text}. ONLY find content directly about this goal topic."
    elif request.context_type == "teaching_candidate":
        return f"Learning goal: {request.goal_text}. Specific topic: {request.teaching_topic}. ONLY find content directly about this specific topic."
    return request.goals_summary or request.goal_text or "general learning"


async def _generate_search_queries(request: FeedRequest) -> List[str]:
    """Use a small LLM call to generate 2-3 search queries for the context."""
    from src.llm_client import LLMClient

    context = _build_context_description(request)
    if request.context_type == "exploration":
        prompt = f"""Given this user's interests and background, generate 3 diverse search queries (each 3-8 words) that span DIFFERENT interests/topics the user has. Each query should target a different area. Return as a JSON array of strings.

IMPORTANT: Generate queries focused on EDUCATIONAL, INTELLECTUAL, and CREATIVE content — articles, essays, academic work, talks, book discussions, technical explainers. NEVER generate queries about dating, relationships, lifestyle advice, or clickbait topics. Focus on substantive learning material.

User context: {context}

Return ONLY a JSON array like: ["query about interest 1", "query about interest 2", "query about interest 3"]"""
    else:
        prompt = f"""Given this learning context, generate 2-3 short search queries (each 3-8 words) that would find relevant articles, videos, and academic papers. Return as a JSON array of strings.

CRITICAL RULES:
- Every query MUST be specifically and directly about the learning goal/topic described below.
- Do NOT generate queries about the user's general background, career, or other interests.
- Do NOT generate generic self-improvement, productivity, or startup queries unless the goal is specifically about those topics.
- Target EDUCATIONAL and INTELLECTUAL content: essays, lectures, research papers, technical discussions, book analyses.
- Avoid anything related to dating, relationships, lifestyle, or clickbait.

Context: {context}

Return ONLY a JSON array like: ["query one", "query two", "query three"]"""

    llm = LLMClient()
    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: llm.chat_with_json(
                    messages=[{"role": "user", "content": prompt}],
                    model="openai:gpt-4o-mini",
                    json_top_level="array",
                    max_retries=2
                )
            ),
            timeout=10.0
        )
        if isinstance(response, list):
            return [str(q) for q in response[:3]]
    except Exception as e:
        print(f"[Feed] Query generation error: {e}")

    # Fallback: use context text directly as a query
    fallback = request.teaching_topic or request.goal_text or request.goals_summary or "learning resources"
    return [fallback]


async def _fetch_all_apis(queries: List[str]) -> List[dict]:
    """Fire all API sources in parallel and collect results."""
    from backend.services.content_apis import (
        fetch_brave_results,
        fetch_youtube_results,
        fetch_semantic_scholar,
        fetch_twitter_results,
        fetch_reddit_results,
        fetch_hackernews_results,
    )

    primary_query = queries[0]
    secondary_query = queries[1] if len(queries) > 1 else queries[0]

    tasks = [
        fetch_brave_results(primary_query, count=4),
        fetch_youtube_results(secondary_query, count=4),
        fetch_twitter_results(primary_query, count=3),
        fetch_reddit_results(secondary_query, count=2),
        fetch_hackernews_results(primary_query, count=2),
        fetch_semantic_scholar(primary_query, count=2),
    ]

    all_items = []
    for coro in asyncio.as_completed(tasks):
        try:
            items = await coro
            all_items.extend(items)
        except Exception as e:
            print(f"[Feed] API fetch error: {e}")

    return _interleave_by_type(all_items)


@router.post("/feed/stream")
async def stream_feed(request: FeedRequest):
    """SSE endpoint that streams feed items as each API returns."""

    async def event_generator():
        t0 = time.time()

        # Phase 0: Clear cache if refresh requested
        if request.refresh:
            try:
                cleared = _db.clear_feed_items(
                    user_id=request.user_id,
                    context_type=request.context_type,
                    goal_id=request.goal_id,
                    teaching_candidate_id=request.teaching_candidate_id
                )
                print(f"[Feed] Cleared {cleared} cached items for refresh")
            except Exception as e:
                print(f"[Feed] Cache clear error: {e}")

        # Phase 0b: Check cache
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
            items = _interleave_by_type(items)
            # Pagination: return a page of items
            page_size = 7
            start = request.page * page_size
            page_items = items[start:start + page_size]
            has_more_cached = (start + page_size) < len(items)

            if page_items:
                for item in page_items:
                    yield f"data: {json.dumps(item)}\n\n"
                # Always say has_more so frontend keeps the sentinel alive;
                # next page will trigger a fresh fetch if cache is exhausted
                yield f"data: {json.dumps({'done': True, 'cached': True, 'count': len(page_items), 'has_more': True})}\n\n"
                print(f"[Feed] Streamed {len(page_items)} cached items (page {request.page}, more_cached={has_more_cached}) in {time.time()-t0:.1f}s")
                return

            # Cache exhausted — fall through to generate a fresh batch
            print(f"[Feed] Cache exhausted at page {request.page}, fetching more...")

        # Collect existing URLs to deduplicate
        existing_urls = set()
        if has_feed:
            existing_items = _db.get_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
            existing_urls = {it.get("source_url") for it in existing_items if it.get("source_url")}

        # Phase 1: Generate search queries
        yield f"data: {json.dumps({'status': 'generating_queries'})}\n\n"
        queries = await _generate_search_queries(request)
        print(f"[Feed] Generated queries: {queries} in {time.time()-t0:.1f}s")
        yield f"data: {json.dumps({'status': 'fetching', 'queries': queries})}\n\n"

        # Phase 2: Fetch from all APIs in parallel, stream as they arrive
        from backend.services.content_apis import (
            fetch_brave_results,
            fetch_youtube_results,
            fetch_semantic_scholar,
            fetch_twitter_results,
            fetch_reddit_results,
            fetch_hackernews_results,
        )

        primary_query = queries[0]
        secondary_query = queries[1] if len(queries) > 1 else queries[0]
        tertiary_query = queries[2] if len(queries) > 2 else primary_query

        # For exploration, use different queries for each API to maximize diversity
        if request.context_type == "exploration":
            tasks = {
                asyncio.create_task(fetch_brave_results(primary_query, count=4)): "brave1",
                asyncio.create_task(fetch_brave_results(tertiary_query, count=4)): "brave2",
                asyncio.create_task(fetch_youtube_results(secondary_query, count=4)): "youtube",
                asyncio.create_task(fetch_twitter_results(primary_query, count=3)): "twitter",
                asyncio.create_task(fetch_reddit_results(secondary_query, count=3)): "reddit",
                asyncio.create_task(fetch_hackernews_results(tertiary_query, count=3)): "hn",
                asyncio.create_task(fetch_semantic_scholar(primary_query, count=2)): "scholar",
            }
        else:
            tasks = {
                asyncio.create_task(fetch_brave_results(primary_query, count=4)): "brave1",
                asyncio.create_task(fetch_brave_results(secondary_query, count=3)): "brave2",
                asyncio.create_task(fetch_youtube_results(secondary_query, count=4)): "youtube",
                asyncio.create_task(fetch_twitter_results(primary_query, count=3)): "twitter",
                asyncio.create_task(fetch_reddit_results(secondary_query, count=2)): "reddit",
                asyncio.create_task(fetch_hackernews_results(primary_query, count=2)): "hn",
                asyncio.create_task(fetch_semantic_scholar(primary_query, count=2)): "scholar",
            }

        all_items = []
        item_id_counter = 0

        # Collect all items first, then interleave and stream
        for task in asyncio.as_completed(list(tasks.keys())):
            try:
                items = await task
                for item in items:
                    # Deduplicate against existing cache
                    url = item.get("source_url")
                    if url and url in existing_urls:
                        continue
                    if url:
                        existing_urls.add(url)
                    item["id"] = item_id_counter
                    item_id_counter += 1
                    all_items.append(item)
            except Exception as e:
                print(f"[Feed] API error: {e}")

        # Interleave so no two consecutive items have the same type
        all_items = _interleave_by_type(all_items)

        # Stream all new items (these append to what the frontend already has)
        page_size = 7
        page_items = all_items[:page_size]
        has_more = len(all_items) > page_size or len(page_items) > 0

        for item in page_items:
            yield f"data: {json.dumps(item)}\n\n"

        # Save ALL new items to DB (appends to existing cache)
        if all_items:
            try:
                _db.save_feed_items(
                    user_id=request.user_id,
                    context_type=request.context_type,
                    items=all_items,
                    goal_id=request.goal_id,
                    teaching_candidate_id=request.teaching_candidate_id
                )
            except Exception as e:
                print(f"[Feed] DB save error: {e}")

        yield f"data: {json.dumps({'done': True, 'cached': False, 'count': len(page_items), 'has_more': has_more})}\n\n"
        print(f"[Feed] Streamed {len(page_items)} new items ({len(all_items)} total fetched, {len(existing_urls)} existing) in {time.time()-t0:.1f}s")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feed", response_model=FeedResponse)
async def get_or_generate_feed(request: FeedRequest):
    """Get feed items for a context, generating if needed."""
    try:
        if request.refresh:
            _db.clear_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )

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

        # No cache — use real APIs via streaming fetcher, then return
        queries = await _generate_search_queries(request)
        all_items = await _fetch_all_apis(queries)

        if not all_items:
            return FeedResponse(items=[], generated=False)

        # Save to DB
        try:
            _db.save_feed_items(
                user_id=request.user_id,
                context_type=request.context_type,
                items=all_items,
                goal_id=request.goal_id,
                teaching_candidate_id=request.teaching_candidate_id
            )
        except Exception as e:
            print(f"[Feed] Failed to save items: {e}")
            import traceback
            traceback.print_exc()
            # Return items even if save fails
            return FeedResponse(
                items=[FeedItemResponse(id=i, **item) for i, item in enumerate(all_items)],
                generated=True
            )

        saved_items = _db.get_feed_items(
            user_id=request.user_id,
            context_type=request.context_type,
            goal_id=request.goal_id,
            teaching_candidate_id=request.teaching_candidate_id
        )
        return FeedResponse(
            items=[FeedItemResponse(**item) for item in saved_items],
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
        cleared = _db.clear_feed_items(
            user_id=user_id,
            context_type=context_type,
            goal_id=goal_id
        )
        return {"success": True, "cleared": cleared, "message": "Feed will be regenerated on next request"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/feed/{user_id}")
async def clear_all_feeds(user_id: str):
    """Clear ALL cached feed items for a user."""
    try:
        cleared = _db.clear_feed_items(user_id=user_id)
        return {"success": True, "cleared": cleared, "message": "All feeds cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
