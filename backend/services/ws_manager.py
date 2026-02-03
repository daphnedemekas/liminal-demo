"""WebSocket connection manager for broadcasting run events."""

import logging
from collections import deque
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_BUFFER_PER_RUN = 200


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

        # Clean up buffer when run completes
        if data.get("type") == "status" and data.get("status") in ("done", "failed"):
            self._buffers.pop(run_id, None)


ws_manager = ConnectionManager()
