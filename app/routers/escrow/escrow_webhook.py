from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from security.webhook_signing import verify_hmac_signature
from settings import settings
from schemas.escrow_chain import ChainDepositWebhook
from services.escrow_webhook_service import (
    enqueue_webhook_retry,
    process_usdc_webhook,
)

router = APIRouter(prefix="/escrow/webhooks", tags=["Escrow Webhooks"])


@router.post("/usdc")
async def usdc_webhook(
    request: Request,
    payload: ChainDepositWebhook,
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    signature = request.headers.get("X-Paylink-Signature")

    if not signature or not verify_hmac_signature(
        raw_body,
        signature,
        settings.ESCROW_WEBHOOK_SECRET,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        return await process_usdc_webhook(db, payload)
    except Exception as exc:
        payload_data = payload.model_dump(mode="json")
        await enqueue_webhook_retry(
            db,
            event_type="USDC_DEPOSIT",
            payload=payload_data,
            last_error=str(exc),
        )
        return {"status": "QUEUED_RETRY"}
