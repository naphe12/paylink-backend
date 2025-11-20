from fastapi import APIRouter, WebSocket, Depends
from app.websocket_manager import admin_ws_join, admin_ws_leave

router = APIRouter()

@router.websocket("/ws/security")
async def ws_security(websocket: WebSocket):
    await admin_ws_join(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        await admin_ws_leave(websocket)
