from typing import Dict
import json
from typing import Dict, Set, List
from fastapi import WebSocket
import json

connected_users: Dict[int, list] = {}  # user_id → list of WebSocket connections

async def register_user(user_id, websocket):
    connected_users.setdefault(user_id, []).append(websocket)

async def unregister_user(user_id, websocket):
    if user_id in connected_users and websocket in connected_users[user_id]:
        connected_users[user_id].remove(websocket)

async def notify_user(user_id: int, message: dict):
    """Envoie un message WebSocket à un utilisateur spécifique"""
    if user_id not in connected_users:
        return
    dead = []
    for ws in connected_users[user_id]:
        try:
            await ws.send_text(json.dumps(message))
        except:
            dead.append(ws)

    # Nettoyage connexions mortes
    for ws in dead:
        connected_users[user_id].remove(ws)


