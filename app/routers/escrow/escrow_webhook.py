import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from app.core.database import get_db
from app.security.rate_limit import rate_limit
from app.config import settings
from app.schemas.escrow_chain import ChainDepositWebhook
from app.services.escrow_webhook_service import (
    enqueue_webhook_retry,
    process_usdc_webhook,
)
from app.services.webhook_log_service import log_webhook

router = APIRouter(prefix="/escrow/webhooks", tags=["Escrow Webhooks"])

async def _ensure_webhook_logs_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS escrow.webhook_logs (
              id bigserial PRIMARY KEY,
              event_type text NOT NULL,
              tx_hash text,
              status text NOT NULL,
              attempts int NOT NULL DEFAULT 1,
              payload jsonb NOT NULL,
              error text,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(text("ALTER TABLE escrow.webhook_logs ADD COLUMN IF NOT EXISTS order_id uuid"))
    await db.execute(text("ALTER TABLE escrow.webhook_logs ADD COLUMN IF NOT EXISTS network text"))


@router.post("/usdc")
async def usdc_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:webhook_usdc", limit=60, window_seconds=60)

    raw_body = await request.body()
    signature = request.headers.get("X-Paylink-Signature")
    secret = settings.HMAC_SECRET or settings.ESCROW_WEBHOOK_SECRET

    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload_dict = await request.json()
    payload = ChainDepositWebhook.model_validate(payload_dict)
    tx_hash = payload_dict.get("tx_hash")
    log_index = payload_dict.get("log_index")

    await _ensure_webhook_logs_schema(db)

    if not tx_hash:
        raise HTTPException(status_code=400, detail="Missing tx_hash")

    # Idempotency guard on the webhook envelope (tx_hash + log_index when provided).
    if log_index is not None:
        dup = await db.execute(
            text(
                """
                SELECT 1
                FROM escrow.webhook_logs
                WHERE tx_hash = :tx
                  AND payload->>'log_index' = :li
                LIMIT 1
                """
            ),
            {"tx": tx_hash, "li": str(log_index)},
        )
    else:
        dup = await db.execute(
            text(
                """
                SELECT 1
                FROM escrow.webhook_logs
                WHERE tx_hash = :tx
                LIMIT 1
                """
            ),
            {"tx": tx_hash},
        )
    if dup.first():
        return {"status": "DUPLICATE"}

    order_id: str | None = None
    try:
        result = await process_usdc_webhook(
            db,
            payload,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        order_id = str(result.get("order_id")) if isinstance(result, dict) and result.get("order_id") else None

        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="SUCCESS",
            payload=payload.model_dump(mode="json"),
            tx_hash=payload.tx_hash,
            order_id=order_id,
            network=payload.network,
        )

        await db.commit()
        return result

    except IntegrityError:
        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="IGNORED_DUPLICATE",
            payload=payload.model_dump(mode="json"),
            tx_hash=payload.tx_hash,
            order_id=order_id,
            network=payload.network,
        )
        await db.rollback()
        return {"status": "DUPLICATE"}

    except Exception as exc:
        payload_data = payload.model_dump(mode="json")
        # If the failure came from SQL execution, the transaction may be aborted.
        # Rollback first so retry/log writes can proceed.
        await db.rollback()

        try:
            await enqueue_webhook_retry(
                db,
                event_type="USDC_DEPOSIT",
                payload=payload_data,
                last_error=str(exc),
                actor_user_id=None,
                actor_role="SYSTEM",
                ip=ip,
                user_agent=request.headers.get("user-agent"),
            )

            await log_webhook(
                db,
                event_type="USDC_DEPOSIT",
                status="FAILED",
                payload=payload_data,
                tx_hash=payload.tx_hash,
                order_id=order_id,
                network=payload.network,
                error=str(exc),
            )

            await db.commit()
        except Exception:
            # Last-resort: do not crash webhook caller if internal retry logging fails.
            await db.rollback()
        return {"status": "QUEUED_RETRY"}
