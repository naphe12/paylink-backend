# app/websocket_manager_security.py
from typing import Set
from starlette.websockets import WebSocket

security_admin_connections: Set[WebSocket] = set()

async def security_push(payload: dict):
    dead = []
    for ws in list(security_admin_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        security_admin_connections.discard(ws)
