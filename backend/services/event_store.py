"""Append-only event logging for agent runs."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.database import RunEvent, get_session_factory


class EventStore:
    def __init__(self):
        self._sequence_counters: dict[str, int] = {}

    def _next_seq(self, run_id: str) -> int:
        seq = self._sequence_counters.get(run_id, 0)
        self._sequence_counters[run_id] = seq + 1
        return seq

    def log(self, run_id: str, event_type: str, payload: dict,
            source_url: str | None = None, source_title: str | None = None) -> RunEvent:
        session = get_session_factory()()
        try:
            ev = RunEvent(
                run_id=run_id,
                sequence=self._next_seq(run_id),
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

    def get_events(self, run_id: str, db: Session | None = None) -> list[RunEvent]:
        if db:
            return db.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.sequence).all()
        session = get_session_factory()()
        try:
            return session.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.sequence).all()
        finally:
            session.close()


event_store = EventStore()
