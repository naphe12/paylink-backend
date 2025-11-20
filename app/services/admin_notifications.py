from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notifications
from app.websocket_manager import ADMIN_NOTIFICATION_TOPICS, notify_security_admins


def _ensure_uuid(value: Union[UUID, str]) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def push_admin_notification(
    topic: str,
    *,
    db: Optional[AsyncSession] = None,
    user_id: Optional[Union[UUID, str]] = None,
    severity: str = "info",
    title: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist (optionally) and broadcast a structured admin notification.
    """

    if topic not in ADMIN_NOTIFICATION_TOPICS:
        raise ValueError(f"Unknown admin notification topic '{topic}'")

    notification_id = uuid4()
    event_timestamp = datetime.now(timezone.utc).isoformat()
    enriched_metadata = {
        "topic": topic,
        "severity": severity,
        **(metadata or {}),
    }

    payload = {
        "id": str(notification_id),
        "topic": topic,
        "severity": severity,
        "title": title,
        "message": message,
        "metadata": enriched_metadata,
        "user_id": str(user_id) if user_id else None,
        "created_at": event_timestamp,
    }

    if db and user_id:
        await db.execute(
            insert(Notifications).values(
                notification_id=notification_id,
                user_id=_ensure_uuid(user_id),
                channel="admin_realtime",
                subject=title,
                message=message,
                metadata_=enriched_metadata,
            )
        )

    await notify_security_admins(topic, payload)
    return payload
