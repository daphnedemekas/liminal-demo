"""FastAPI routers for the Liminal Discovery System."""
from .auth import router as auth_router
from .discovery import router as discovery_router
from .teaching import router as teaching_router
from .feed import router as feed_router
from .terminal import router as terminal_router
from .documents import router as documents_router
from .trajectory import router as trajectory_router

__all__ = [
    "auth_router",
    "discovery_router",
    "teaching_router",
    "feed_router",
    "terminal_router",
    "documents_router",
    "trajectory_router",
]
