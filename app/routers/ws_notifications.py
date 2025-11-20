from fastapi import APIRouter, Depends, WebSocket

from app.dependencies.auth import get_current_user_ws
from app.websocket_manager import manager

router = APIRouter()

@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket, user = Depends(get_current_user_ws)):
    user_id = str(user.user_id)
    await manager.connect(user_id, websocket)
    
    try:
        while True:
            await websocket.receive_text()  # Keep alive / ping
    except:
        manager.disconnect(user_id)
