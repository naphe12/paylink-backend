# app/realtime/manager.py
import json
from typing import Dict, Set

from starlette.websockets import WebSocket


class WSManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self.rooms: Dict[str, Set[WebSocket]] = {}  # room = tontine_id

    async def connect(self, websocket: WebSocket, rooms: list[str] | None = None):
        await websocket.accept()
        self.active.add(websocket)
        if rooms:
            for r in rooms:
                self.rooms.setdefault(r, set()).add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active.discard(websocket)
        for r in list(self.rooms.keys()):
            self.rooms[r].discard(websocket)
            if not self.rooms[r]:
                self.rooms.pop(r, None)

    async def send_json(self, websocket: WebSocket, data: dict):
        await websocket.send_text(json.dumps(data))

    async def broadcast_tontine_event(self, tontine_id: str, event_type: str, payload: dict):
        for ws in self.rooms.get(tontine_id, set()):
            await self.send_json(ws, {"type": event_type, "tontine_id": tontine_id, "data": payload})

ws_manager = WSManager()
