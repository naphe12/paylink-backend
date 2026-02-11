from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.services.audit_service import audit_log
from app.services.escrow_webhook_service import enqueue_webhook_retry

router = APIRouter(prefix="/backoffice/webhooks", tags=["Backoffice - Webhooks"])


@router.get("")
async def list_webhook_logs(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS escrow.webhook_logs (
              id bigserial PRIMARY KEY,
              event_type text NOT NULL,
              tx_hash text,
              status text NOT NULL,
              attempts int NOT NULL DEFAULT 0,
              payload jsonb NOT NULL,
              error text,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    rows = (
        await db.execute(
            text(
                """
                SELECT id, event_type, tx_hash, status, attempts, payload, error, created_at
                FROM escrow.webhook_logs
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/{log_id}/retry")
async def retry_webhook_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    role = str(getattr(user, "role", "")).lower()
    if role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")

    row = (
        await db.execute(
            text(
                """
                SELECT id, event_type, tx_hash, payload
                FROM escrow.webhook_logs
                WHERE id = :id
                """
            ),
            {"id": log_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Webhook log introuvable")

    payload = row._mapping["payload"]
    event_type = row._mapping["event_type"]
    tx_hash = row._mapping["tx_hash"]
    actor_id = getattr(user, "id", None) or getattr(user, "user_id", None)
    actor_role = str(getattr(user, "role", "") or "")

    await enqueue_webhook_retry(
        db,
        event_type=str(event_type),
        payload=dict(payload or {}),
        last_error="MANUAL_RETRY_REQUESTED",
        actor_user_id=str(actor_id) if actor_id else None,
        actor_role=actor_role,
    )
    await audit_log(
        db,
        actor_user_id=str(actor_id) if actor_id else None,
        actor_role=actor_role,
        action="WEBHOOK_RETRY_MANUAL",
        entity_type="escrow_webhook",
        entity_id=None,
        before_state=None,
        after_state={
            "event_type": str(event_type),
            "tx_hash": tx_hash,
            "source_log_id": int(log_id),
        },
        ip=None,
        user_agent=None,
    )
    await db.commit()
    return {"status": "QUEUED_RETRY", "source_log_id": int(log_id), "event_type": str(event_type), "tx_hash": tx_hash}
