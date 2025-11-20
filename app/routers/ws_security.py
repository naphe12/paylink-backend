# app/routers/ws_security.py
from fastapi import APIRouter, WebSocket, Depends
from app.core.security import admin_required_ws
from app.websocket_manager_security import security_admin_connections

router = APIRouter()

@router.websocket("/ws/security")
async def ws_security(websocket: WebSocket):
    await websocket.accept()
    security_admin_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except Exception:
        security_admin_connections.discard(websocket)
