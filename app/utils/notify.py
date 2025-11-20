# app/utils/notify.py
from app.routers.notifications.websocket import active_connections
from app.utils.logger import log_info, log_warning


async def send_notification(user_id: str, message: str):
    """
    🔔 Envoie une notification instantanée via WebSocket à un utilisateur.
    """
    ws = active_connections.get(user_id)
    if ws:
        try:
            await ws.send_json({"message": message})
            log_info(f"📩 Notification envoyée à {user_id} : {message}")
        except Exception as e:
            log_warning(f"⚠️ Erreur d’envoi à {user_id} : {e}")
    else:
        log_warning(f"ℹ️ Aucun WebSocket actif pour {user_id}")

