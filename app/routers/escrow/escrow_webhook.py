from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.security.webhook_signing import verify_hmac_signature
from app.security.rate_limit import rate_limit
from app.config import settings
from app.schemas.escrow_chain import ChainDepositWebhook
from app.services.escrow_webhook_service import (
    enqueue_webhook_retry,
    process_usdc_webhook,
)
from app.services.webhook_log_service import log_webhook

router = APIRouter(prefix="/escrow/webhooks", tags=["Escrow Webhooks"])


@router.post("/usdc")
async def usdc_webhook(
    request: Request,
    payload: ChainDepositWebhook,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:webhook_usdc", limit=60, window_seconds=60)

    raw_body = await request.body()
    signature = request.headers.get("X-Paylink-Signature")

    if not signature or not verify_hmac_signature(
        raw_body,
        signature,
        settings.ESCROW_WEBHOOK_SECRET,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

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
        return {"status": "QUEUED_RETRY"}
