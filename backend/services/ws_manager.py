"""WebSocket connection manager for broadcasting run events."""

import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket connections per run_id and broadcasts events."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: str, ws: WebSocket):
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)

    async def broadcast(self, run_id: str, data: dict):
        conns = self._connections.get(run_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


ws_manager = ConnectionManager()
