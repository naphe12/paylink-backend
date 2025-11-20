from typing import Dict, Set, List, Optional
from fastapi import WebSocket
import json

# =============================
# ROOMS (ex: Tontines, Groupes)
# =============================
rooms: Dict[str, Set[WebSocket]] = {}


async def ws_join(room_id: str, websocket: WebSocket):
    if room_id not in rooms:
        rooms[room_id] = set()
    rooms[room_id].add(websocket)
    await websocket.accept()


async def ws_leave(room_id: str, websocket: WebSocket):
    if room_id in rooms and websocket in rooms[room_id]:
        rooms[room_id].remove(websocket)
    try:
        await websocket.close()
    except:
        pass


async def ws_push_room(room_id: str, message: dict):
    if room_id not in rooms:
        return

    dead = []
    for ws in rooms[room_id]:
        try:
            await ws.send_json(message)
        except:
            dead.append(ws)

    for ws in dead:
        rooms[room_id].remove(ws)


# =============================
# ADMIN SECURITE (diffusion globale)
# =============================
ADMIN_NOTIFICATION_TOPICS: Dict[str, str] = {
    "agent_created": "Nouveaux agents",
    "aml_high": "Alertes AML",
    "mobilemoney_failed": "Mobile money",
    "kyc_reset": "Reinitialisations KYC",
}

security_admin_connections: Dict[WebSocket, Optional[Set[str]]] = {}


async def admin_ws_join(ws: WebSocket, topics: Optional[Set[str]] = None):
    await ws.accept()
    if topics:
        allowed = {topic for topic in topics if topic in ADMIN_NOTIFICATION_TOPICS}
        security_admin_connections[ws] = allowed or None
    else:
        security_admin_connections[ws] = None


async def admin_ws_leave(ws: WebSocket):
    security_admin_connections.pop(ws, None)


async def notify_security_admins(topic: str, payload: dict):
    if topic not in ADMIN_NOTIFICATION_TOPICS:
        raise ValueError(f"Unknown admin notification topic '{topic}'")

    enriched_payload = {**payload, "topic": topic}

    dead: List[WebSocket] = []
    for ws, allowed_topics in security_admin_connections.items():
        if allowed_topics and topic not in allowed_topics:
            continue
        try:
            await ws.send_json(enriched_payload)
        except:
            dead.append(ws)

    for ws in dead:
        security_admin_connections.pop(ws, None)


# =============================
# NOTIFICATION UTILISATEUR CIBLÉ
# =============================
connected_users: Dict[int, List[WebSocket]] = {}


async def register_user(user_id: int, websocket: WebSocket):
    await websocket.accept()
    connected_users.setdefault(user_id, []).append(websocket)


async def unregister_user(user_id: int, websocket: WebSocket):
    if user_id in connected_users and websocket in connected_users[user_id]:
        connected_users[user_id].remove(websocket)


async def notify_user(user_id: int, message: dict):
    if user_id not in connected_users:
        return

    dead = []
    for ws in connected_users[user_id]:
        try:
            await ws.send_text(json.dumps(message))
        except:
            dead.append(ws)

    for ws in dead:
        connected_users[user_id].remove(ws)


# =============================
# MANAGER SIMPLE (ex: pour live dashboard)
# =============================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict):
        ws = self.active_connections.get(user_id)
        if not ws:
            return
        try:
            await ws.send_json(message)
        except:
            self.disconnect(user_id)


manager = ConnectionManager()

