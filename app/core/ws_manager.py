from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: DefaultDict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, order_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[order_id].add(websocket)

    def disconnect(self, order_id: str, websocket: WebSocket) -> None:
        conns = self.active_connections.get(order_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self.active_connections.pop(order_id, None)

    async def broadcast(self, order_id: str, message: dict) -> None:
        conns = list(self.active_connections.get(order_id, set()))
        if not conns:
            return
        dead: list[WebSocket] = []
        for connection in conns:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for websocket in dead:
            self.disconnect(order_id, websocket)


manager = ConnectionManager()
