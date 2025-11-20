from fastapi import APIRouter, Depends, Query, WebSocket

from app.core.security import admin_required
from app.websocket_manager import admin_ws_join, admin_ws_leave

router = APIRouter()


@router.websocket("/ws/admin")
async def admin_ws(
    ws: WebSocket,
    token: str = Query(...),
    topics: str | None = Query(default=None),
    admin=Depends(admin_required),
):
    topic_set = {t.strip() for t in (topics or "").split(",") if t.strip()}
    await admin_ws_join(ws, topic_set or None)
    try:
        while True:
            await ws.receive_text()
    except:
        await admin_ws_leave(ws)
