from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.notifications import Notifications
from app.websocket_manager import ADMIN_NOTIFICATION_TOPICS

router = APIRouter(prefix="/admin/notifications", tags=["Admin Notifications"])


@router.get("/")
async def list_admin_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    topic: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(Notifications)
        .where(Notifications.channel == "admin_realtime")
        .order_by(Notifications.created_at.desc())
        .limit(limit)
    )

    if topic:
        if topic not in ADMIN_NOTIFICATION_TOPICS:
            raise HTTPException(400, "Topic inconnu")
        stmt = stmt.where(Notifications.metadata_["topic"].astext == topic)

    rows = (await db.execute(stmt)).scalars().all()

    payload = []
    for row in rows:
        metadata = row.metadata_ or {}
        payload.append(
            {
                "id": str(row.notification_id),
                "user_id": str(row.user_id) if row.user_id else None,
                "subject": row.subject,
                "message": row.message,
                "topic": metadata.get("topic"),
                "severity": metadata.get("severity"),
                "metadata": metadata,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return payload
