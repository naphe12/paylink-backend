from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.escrow_order import EscrowOrder
from app.models.users import Users
from app.schemas.escrow_chain import ChainDepositWebhook
from app.services.audit_service import audit_log
from app.services.escrow_webhook_service import enqueue_webhook_retry
from app.services.escrow_webhook_service import process_usdc_webhook

router = APIRouter(prefix="/backoffice/webhooks", tags=["Backoffice - Webhooks"])


class SandboxUsdcWebhookIn(BaseModel):
    order_id: str
    amount: Decimal = Field(gt=Decimal("0"))
    confirmations: int = Field(default=3, ge=0)
    tx_hash: str | None = None
    from_address: str | None = None


@router.get("/providers")
async def list_webhook_providers(
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")

    where = ["TRIM(COALESCE(payload->>'provider', '')) <> ''"]
    params = {}
    if event_type:
        where.append("event_type = :event_type")
        params["event_type"] = event_type

    sql = """
        SELECT DISTINCT TRIM(COALESCE(payload->>'provider', '')) AS provider
        FROM escrow.webhook_logs
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY provider ASC"

    rows = (await db.execute(text(sql), params)).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


@router.get("/stats")
async def webhook_stats(
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")

    where = []
    params = {}
    if event_type:
        where.append("event_type = :event_type")
        params["event_type"] = event_type

    total_sql = """
        SELECT
          COUNT(*)::int AS total,
          COUNT(*) FILTER (WHERE upper(status) = 'SUCCESS')::int AS success,
          COUNT(*) FILTER (WHERE upper(status) = 'DUPLICATE')::int AS duplicate,
          COUNT(*) FILTER (WHERE upper(status) = 'FAILED')::int AS failed
        FROM escrow.webhook_logs
    """
    by_provider_sql = """
        SELECT
          TRIM(COALESCE(payload->>'provider', 'unknown')) AS provider,
          COUNT(*)::int AS total,
          COUNT(*) FILTER (WHERE upper(status) = 'SUCCESS')::int AS success,
          COUNT(*) FILTER (WHERE upper(status) = 'DUPLICATE')::int AS duplicate,
          COUNT(*) FILTER (WHERE upper(status) = 'FAILED')::int AS failed
        FROM escrow.webhook_logs
    """
    if where:
        clause = " WHERE " + " AND ".join(where)
        total_sql += clause
        by_provider_sql += clause
    by_provider_sql += """
        GROUP BY TRIM(COALESCE(payload->>'provider', 'unknown'))
        ORDER BY total DESC, provider ASC
        """

    total_row = (await db.execute(text(total_sql), params)).mappings().first()
    provider_rows = (await db.execute(text(by_provider_sql), params)).mappings().all()
    return {
        "total": int((total_row or {}).get("total") or 0),
        "success": int((total_row or {}).get("success") or 0),
        "duplicate": int((total_row or {}).get("duplicate") or 0),
        "failed": int((total_row or {}).get("failed") or 0),
        "by_provider": [
            {
                "provider": str(item["provider"] or "unknown"),
                "total": int(item["total"] or 0),
                "success": int(item["success"] or 0),
                "duplicate": int(item["duplicate"] or 0),
                "failed": int(item["failed"] or 0),
            }
            for item in provider_rows
        ],
    }


@router.get("")
async def list_webhook_logs(
    limit: int = 200,
    event_type: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    query: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")
    where = []
    params = {"limit": limit}
    if event_type:
        where.append("event_type = :event_type")
        params["event_type"] = event_type
    if status:
        where.append("status = :status")
        params["status"] = status
    if provider:
        where.append("COALESCE(payload->>'provider', '') = :provider")
        params["provider"] = provider
    if query:
        where.append(
            """
            (
              COALESCE(event_type, '') ILIKE :pattern
              OR COALESCE(tx_hash, '') ILIKE :pattern
              OR COALESCE(status, '') ILIKE :pattern
              OR COALESCE(payload->>'provider', '') ILIKE :pattern
              OR COALESCE(payload->>'provider_event_id', '') ILIKE :pattern
              OR CAST(payload AS text) ILIKE :pattern
            )
            """
        )
        params["pattern"] = f"%{query.strip()}%"

    sql = """
        SELECT id, event_type, tx_hash, status, attempts, payload, error, created_at
        FROM escrow.webhook_logs
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT :limit"
    rows = (await db.execute(text(sql), params)).fetchall()
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


@router.post("/sandbox/usdc")
async def sandbox_usdc_webhook(
    payload: SandboxUsdcWebhookIn,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    role = str(getattr(user, "role", "")).lower()
    if role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")

    order = await db.get(EscrowOrder, payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order introuvable")

    flags = [str(f) for f in list(getattr(order, "flags", []) or [])]
    if "SANDBOX" not in flags:
        raise HTTPException(status_code=400, detail="Action reservee aux ordres escrow sandbox")
    if not order.deposit_address:
        raise HTTPException(status_code=400, detail="Order sans deposit_address")

    tx_hash = (payload.tx_hash or f"0xsandbox{uuid4().hex}").strip()
    from_address = (payload.from_address or "0x000000000000000000000000000000000000dEaD").strip()

    chain_payload = ChainDepositWebhook(
        network=order.deposit_network,
        tx_hash=tx_hash,
        from_address=from_address,
        to_address=str(order.deposit_address),
        amount=payload.amount,
        confirmations=payload.confirmations,
    )

    result = await process_usdc_webhook(
        db,
        chain_payload,
        ip="backoffice",
        user_agent="backoffice-sandbox-usdc",
    )
    await db.commit()
    return {
        "status": "OK",
        "result": result,
        "payload": chain_payload.model_dump(mode="json"),
        "order_id": str(order.id),
    }
