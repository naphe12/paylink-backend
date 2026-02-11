from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.security.webhook_hmac import verify_signature
from app.services.webhook_log_service import log_webhook
from app.services.escrow_webhook_service import process_usdc_webhook  # ton service

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

@router.post("/usdc")
async def usdc_webhook(
    request: Request,
    x_signature: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    raw = await request.body()

    if not verify_signature(raw, x_signature):
        raise HTTPException(401, "Invalid signature")

    payload = await request.json()
    tx_hash = payload.get("tx_hash")
    network = payload.get("network")
    order_id = payload.get("order_id")  # si dispo

    try:
        # ton traitement doit écrire chain_deposit avec tx_hash unique
        await process_usdc_webhook(db, payload)

        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="SUCCESS",
            payload=payload,
            tx_hash=tx_hash,
            order_id=order_id,
            network=network,
        )
        await db.commit()
        return {"ok": True}

    except IntegrityError:
        # tx_hash déjà traité
        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="IGNORED_DUPLICATE",
            payload=payload,
            tx_hash=tx_hash,
            order_id=order_id,
            network=network,
        )
        await db.rollback()
        return {"ok": True, "duplicate": True}

    except Exception as e:
        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="FAILED",
            payload=payload,
            tx_hash=tx_hash,
            order_id=order_id,
            network=network,
            error=str(e),
        )
        await db.commit()
        raise
