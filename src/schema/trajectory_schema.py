"""Pydantic models for the Learner Trajectory dashboard state."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class TrajectoryHighlight(BaseModel):
    id: Optional[str] = None
    timestamp: Optional[str] = None
    kind: str = "insight"  # insight | learned | goal_progress | engagement | system_update
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quote: Optional[str] = None
    source_session_id: Optional[str] = None
    goal_id: Optional[int] = None


class TrajectoryGoal(BaseModel):
    goal_id: int
    goal_text: str = ""
    status: str = "active"  # active | paused | completed | archived
    momentum: str = "unknown"  # moving | stuck | inactive | unknown
    last_activity_at: Optional[str] = None
    learning_summary: str = ""
    next_suggested_move: str = ""


class LearnerTrajectoryDashboard(BaseModel):
    """Canonical longitudinal dashboard state, stored as JSON and rendered in the UI."""

    version: int = 1
    user_id: str
    updated_at: Optional[str] = None

    # Cross-cutting insights that connect themes across all sessions
    insights: str = ""  # 2-3 sentences about underlying patterns connecting their interests

    highlights: List[TrajectoryHighlight] = Field(default_factory=list)
    goals: List[TrajectoryGoal] = Field(default_factory=list)

    # Keep these flexible in V1; we can harden later.
    engagement: Dict[str, Any] = Field(default_factory=dict)
    learner_model: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


