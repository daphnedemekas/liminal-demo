"""Insights API — expose user insights to frontend."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import Insight, get_db

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
def get_insights(user_id: str = Query(...), db: Session = Depends(get_db)):
    """Return all active insights for a user, grouped by category with timeline."""
    rows = (
        db.query(Insight)
        .filter_by(user_id=user_id)
        .filter(Insight.superseded_by.is_(None))
        .order_by(Insight.created_at.desc())
        .all()
    )

    def _iso(dt):
        """Format datetime as ISO with Z suffix so JS treats it as UTC."""
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    categories: dict[str, list] = defaultdict(list)
    for r in rows:
        categories[r.category].append({
            "id": r.id,
            "content": r.content,
            "confidence": r.confidence,
            "source_layer": r.source_layer,
            "created_at": _iso(r.created_at),
        })

    recent = [
        {
            "id": r.id,
            "content": r.content,
            "category": r.category,
            "confidence": r.confidence,
            "source_layer": r.source_layer,
            "created_at": _iso(r.created_at),
        }
        for r in rows[:10]
    ]

    # Timeline: count per week for last 8 weeks
    now = datetime.now(timezone.utc)
    weeks: list[dict] = []
    for i in range(7, -1, -1):
        week_start = now - timedelta(weeks=i + 1)
        week_end = now - timedelta(weeks=i)
        count = sum(
            1 for r in rows
            if r.created_at and week_start <= r.created_at.replace(tzinfo=timezone.utc) < week_end
        )
        weeks.append({"week": week_start.strftime("%Y-%m-%d"), "count": count})

    return {
        "total_count": len(rows),
        "categories": dict(categories),
        "recent": recent,
        "timeline": weeks,
    }
