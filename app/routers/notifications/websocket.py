# app/routers/notifications.py
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token

router = APIRouter(prefix="/ws", tags=["Notifications"])

# ✅ Dictionnaire pour stocker les connexions actives
active_connections: Dict[str, WebSocket] = {}

@router.websocket("/notifications")
async def websocket_endpoint(websocket: WebSocket):
    # 🔹 Accepter la connexion
    await websocket.accept()

    # 🔹 Authentifier via le token (passé dans le query param ?token=xxx)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=4002)
        return

    user_id = payload["sub"]
    active_connections[user_id] = websocket
    print(f"✅ WebSocket connecté : {user_id}")

    try:
        while True:
            await websocket.receive_text()  # on ne reçoit rien, juste garde la connexion
    except WebSocketDisconnect:
        print(f"❌ Déconnexion WebSocket : {user_id}")
        active_connections.pop(user_id, None)

