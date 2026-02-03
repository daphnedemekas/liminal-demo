"""WebSocket connection manager for broadcasting run events."""

import asyncio
import logging
from collections import deque
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_BUFFER_PER_RUN = 200
BUFFER_CLEANUP_DELAY = 60.0  # Keep buffer for 60s after run completion


class ConnectionManager:
    """Tracks WebSocket connections per run_id and broadcasts events."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._buffers: Dict[str, deque] = {}

    async def connect(self, run_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)
        # Replay buffered events to late-connecting client
        for data in self._buffers.get(run_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                break

    def disconnect(self, run_id: str, ws: WebSocket):
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)

    async def broadcast(self, run_id: str, data: dict):
        # Buffer the event for late-connecting clients
        buf = self._buffers.setdefault(run_id, deque(maxlen=MAX_BUFFER_PER_RUN))
        buf.append(data)

        conns = self._connections.get(run_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)

        # Delay buffer cleanup so clients that reconnect after a run completes
        # can still receive the final events (especially the synthesis).
        if data.get("type") == "status" and data.get("status") in ("done", "failed"):
            asyncio.create_task(self._delayed_cleanup(run_id))

    async def _delayed_cleanup(self, run_id: str):
        """Clean up event buffer after a delay, allowing late reconnections."""
        await asyncio.sleep(BUFFER_CLEANUP_DELAY)
        self._buffers.pop(run_id, None)


ws_manager = ConnectionManager()
