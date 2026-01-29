"""Real content API fetchers for feed generation."""
import os
import re
import httpx
from typing import List, Dict, Any, Optional

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

TIMEOUT = 5.0


async def fetch_brave_results(query: str, count: int = 3) -> List[Dict[str, Any]]:
    """Fetch article/blog results from Brave Search."""
    if not BRAVE_API_KEY:
        print("[ContentAPIs] No BRAVE_API_KEY set, skipping Brave search")
        return []

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": count, "text_decorations": "false"},
                headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in (data.get("web", {}).get("results", []))[:count]:
            url = item.get("url", "")
            # Skip Twitter/Reddit/Wikipedia — dedicated fetchers or low-value
            if any(d in url for d in ["x.com", "twitter.com", "reddit.com", "wikipedia.org"]):
                continue
            results.append({
                "title": item.get("title", ""),
                "content": item.get("description", ""),
                "source_citation": _extract_domain(url),
                "source_url": url,
                "source_type": "article",
                "thumbnail_url": (item.get("thumbnail", {}) or {}).get("src"),
            })
        print(f"[ContentAPIs] Brave search returned {len(results)} articles for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] Brave search error: {e}")
        return []


def _extract_domain(url: str) -> str:
    """Extract a clean domain name from URL for citation."""
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
        return hostname.replace("www.", "")
    except Exception:
        return url


def _extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from a URL."""
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def fetch_youtube_results(query: str, count: int = 2) -> List[Dict[str, Any]]:
    """Fetch YouTube videos sorted by view count. Uses YouTube Data API if key
    is available (free tier: ~100 searches/day), falls back to Brave Search."""
    if YOUTUBE_API_KEY:
        return await _fetch_youtube_via_api(query, count)
    elif BRAVE_API_KEY:
        return await _fetch_youtube_via_brave(query, count)
    else:
        print("[ContentAPIs] No YOUTUBE_API_KEY or BRAVE_API_KEY set, skipping YouTube")
        return []


def _format_view_count(views: int) -> str:
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    elif views >= 1_000:
        return f"{views / 1_000:.0f}K views"
    return f"{views:,} views"


async def _fetch_youtube_via_api(query: str, count: int) -> List[Dict[str, Any]]:
    """Fetch YouTube videos using the official Data API, sorted by view count."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Step 1: Search for videos sorted by viewCount
            resp = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "order": "viewCount",
                    "maxResults": count,
                    "key": YOUTUBE_API_KEY,
                },
            )
            resp.raise_for_status()
            search_data = resp.json()

            video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
            if not video_ids:
                return []

            # Step 2: Get view counts for the videos
            stats_resp = await client.get(
                YOUTUBE_VIDEOS_URL,
                params={
                    "part": "statistics",
                    "id": ",".join(video_ids),
                    "key": YOUTUBE_API_KEY,
                },
            )
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

        # Build view count map
        view_counts = {}
        for item in stats_data.get("items", []):
            view_counts[item["id"]] = int(item.get("statistics", {}).get("viewCount", 0))

        results = []
        for item in search_data.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item.get("snippet", {})
            views = view_counts.get(video_id, 0)
            results.append({
                "title": snippet.get("title", ""),
                "content": snippet.get("description", "")[:200],
                "source_citation": f"YouTube · {_format_view_count(views)}",
                "source_url": f"https://www.youtube.com/watch?v={video_id}",
                "source_type": "video",
                "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url")
                    or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
                "engagement": views,
            })
        print(f"[ContentAPIs] YouTube API returned {len(results)} videos for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] YouTube API error: {e}")
        return []


async def _fetch_youtube_via_brave(query: str, count: int) -> List[Dict[str, Any]]:
    """Fallback: fetch YouTube results via Brave Search (no view counts)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={
                    "q": f"site:youtube.com {query}",
                    "count": count + 3,
                    "text_decorations": "false",
                },
                headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            if len(results) >= count:
                break
            url = item.get("url", "")
            video_id = _extract_youtube_id(url)
            if not video_id:
                continue
            results.append({
                "title": item.get("title", ""),
                "content": item.get("description", ""),
                "source_citation": f"YouTube",
                "source_url": url,
                "source_type": "video",
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
            })
        print(f"[ContentAPIs] YouTube (Brave fallback) returned {len(results)} videos for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] YouTube (Brave) error: {e}")
        return []


async def fetch_semantic_scholar(query: str, count: int = 2) -> List[Dict[str, Any]]:
    """Fetch academic papers from Semantic Scholar (free, no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                SEMANTIC_SCHOLAR_URL,
                params={
                    "query": query,
                    "limit": count + 3,  # fetch extra to filter low-citation papers
                    "fields": "title,abstract,url,year,authors,externalIds,citationCount",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Sort by citation count to surface more influential papers
        papers = data.get("data", [])
        papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)

        results = []
        for paper in papers[:count]:
            authors = paper.get("authors", [])
            author_str = ", ".join(a.get("name", "") for a in authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            year = paper.get("year", "")
            citations = paper.get("citationCount") or 0
            citation = f"{author_str} ({year})" if author_str and year else author_str or str(year)
            if citations > 0:
                citation += f" · {citations:,} citations"

            # Build URL - prefer Semantic Scholar URL
            paper_url = paper.get("url", "")
            ext_ids = paper.get("externalIds") or {}
            if not paper_url and ext_ids.get("DOI"):
                paper_url = f"https://doi.org/{ext_ids['DOI']}"

            results.append({
                "title": paper.get("title", ""),
                "content": (paper.get("abstract") or "No abstract available.")[:300],
                "source_citation": citation,
                "source_url": paper_url,
                "source_type": "paper",
                "engagement": citations,
            })
        print(f"[ContentAPIs] Semantic Scholar returned {len(results)} papers for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] Semantic Scholar error: {e}")
        return []


async def fetch_twitter_results(query: str, count: int = 2) -> List[Dict[str, Any]]:
    """Fetch popular tweets via Brave Search. Surfaces high-engagement tweets
    since search engines index popular content."""
    if not BRAVE_API_KEY:
        print("[ContentAPIs] No BRAVE_API_KEY set, skipping Twitter search")
        return []

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={
                    "q": f"site:x.com {query}",
                    "count": count + 4,
                    "text_decorations": "false",
                },
                headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            if len(results) >= count:
                break
            url = item.get("url", "")
            # Only include actual tweet URLs (not profiles or lists)
            if "/status/" not in url:
                continue
            # Extract author from URL pattern x.com/username/status/...
            author_match = re.search(r'x\.com/([^/]+)/status/', url)
            author = f"@{author_match.group(1)}" if author_match else "X"
            results.append({
                "title": item.get("title", ""),
                "content": item.get("description", "")[:280],
                "source_citation": f"{author} on X",
                "source_url": url,
                "source_type": "tweet",
            })
        print(f"[ContentAPIs] Twitter search returned {len(results)} tweets for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] Twitter search error: {e}")
        return []


async def fetch_reddit_results(query: str, count: int = 2) -> List[Dict[str, Any]]:
    """Fetch top Reddit posts and extract what they link to.
    Uses Reddit's JSON API to get the actual linked content, not just the discussion."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.reddit.com/search.json",
                params={
                    "q": query,
                    "sort": "relevance",
                    "t": "year",
                    "limit": count + 20,  # Fetch extra since we allowlist subreddits
                },
                headers={"User-Agent": "liminal-feed/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Only allow educational/academic/intellectual subreddits
        ALLOWED_SUBREDDITS = {
            "science", "askscience", "askhistorians", "explainlikeimfive",
            "physics", "math", "mathematics", "computerscience", "machinelearning",
            "artificial", "philosophy", "linguistics", "neuroscience", "biology",
            "chemistry", "astronomy", "space", "engineering",
            "literature", "books", "poetry", "truefilm", "musictheory",
            "deeplearning", "datascience", "statistics",
            "history", "economics", "psychology",
            "learnprogramming", "compsci", "coding",
            "lectures", "documentaries", "todayilearned",
            "startups", "entrepreneur",
        }

        results = []
        for child in data.get("data", {}).get("children", []):
            if len(results) >= count:
                break
            post = child.get("data", {})
            score = post.get("score", 0)
            if score < 10:
                continue  # Skip low-engagement posts

            # Only include posts from educational subreddits
            subreddit_name = post.get("subreddit", "").lower()
            if subreddit_name not in ALLOWED_SUBREDDITS:
                continue

            # Basic relevance filter: at least one query keyword must appear in title or content
            query_words = [w.lower() for w in query.split() if len(w) > 3]
            post_text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
            if query_words and not any(w in post_text for w in query_words):
                continue

            subreddit = post.get("subreddit_name_prefixed", "Reddit")
            post_url = post.get("url", "")
            permalink = f"https://www.reddit.com{post.get('permalink', '')}"

            # If the post links to external content, use that URL
            is_self = post.get("is_self", True)
            is_reddit_link = "reddit.com" in post_url or "redd.it" in post_url
            source_url = post_url if (not is_self and not is_reddit_link and post_url) else permalink
            content = (post.get("selftext") or post.get("title", ""))[:300]

            results.append({
                "title": post.get("title", ""),
                "content": content,
                "source_citation": f"{subreddit} · {score:,} upvotes",
                "source_url": source_url,
                "source_type": "discussion",
                "engagement": score,
            })

        # Sort by engagement
        results.sort(key=lambda r: r.get("engagement", 0), reverse=True)
        print(f"[ContentAPIs] Reddit search returned {len(results)} posts for: {query}")
        return results[:count]
    except Exception as e:
        print(f"[ContentAPIs] Reddit search error: {e}")
        return []


async def fetch_hackernews_results(query: str, count: int = 2) -> List[Dict[str, Any]]:
    """Fetch popular Hacker News posts via Algolia API (free, no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                HN_SEARCH_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": count + 3,
                    "numericFilters": "points>50",  # Only popular posts
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Sort by points to get most popular
        hits = data.get("hits", [])
        hits.sort(key=lambda h: h.get("points", 0), reverse=True)

        results = []
        for hit in hits[:count]:
            points = hit.get("points", 0)
            num_comments = hit.get("num_comments", 0)
            hn_url = f"https://news.ycombinator.com/item?id={hit['objectID']}"
            # Prefer the actual article URL if available
            source_url = hit.get("url") or hn_url
            results.append({
                "title": hit.get("title", ""),
                "content": f"Discussion on Hacker News with {points} points and {num_comments} comments.",
                "source_citation": f"Hacker News · {points} points",
                "source_url": source_url,
                "source_type": "discussion",
                "engagement": points,
            })
        print(f"[ContentAPIs] HN search returned {len(results)} posts for: {query}")
        return results
    except Exception as e:
        print(f"[ContentAPIs] HN search error: {e}")
        return []
