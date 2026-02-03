"""Append-only event logging for agent runs."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import RunEvent, get_session_factory


class EventStore:
    def log(self, run_id: str, event_type: str, payload: dict,
            source_url: Optional[str] = None, source_title: Optional[str] = None) -> RunEvent:
        session = get_session_factory()()
        try:
            max_seq = (
                session.query(func.max(RunEvent.sequence))
                .filter_by(run_id=run_id)
                .scalar()
            )
            next_seq = (max_seq or -1) + 1
            ev = RunEvent(
                run_id=run_id,
                sequence=next_seq,
                event_type=event_type,
                payload=payload,
                source_url=source_url,
                source_title=source_title,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(ev)
            session.commit()
            session.refresh(ev)
            return ev
        finally:
            session.close()

    def get_events(self, run_id: str, db: Optional[Session] = None) -> List[RunEvent]:
        if db:
            return db.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.sequence).all()
        session = get_session_factory()()
        try:
            events = session.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.sequence).all()
            # Eagerly expire and detach so callers don't hit DetachedInstanceError
            session.expunge_all()
            return events
        finally:
            session.close()


event_store = EventStore()
