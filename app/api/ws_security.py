from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.websocket_manager import security_admin_connections
from app.core.security import get_current_user
from app.models.users import Users

router = APIRouter()

@router.websocket("/ws/security")
async def ws_security_monitor(websocket: WebSocket, token: str):
    """
    Canal réservé aux utilisateurs ROLE=admin pour monitoring AML.
    """
    # Vérification Token
    user = get_current_user(token)  # ou decode directement si tu veux

    if user.role != "admin":
        await websocket.close(code=4403)  # Forbidden
        return

    await websocket.accept()
    security_admin_connections.add(websocket)

    try:
        while True:
            await websocket.receive_text()  # Admins ne parlent pas → juste écouter
    except WebSocketDisconnect:
        security_admin_connections.remove(websocket)
