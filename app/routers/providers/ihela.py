import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.security.rate_limit import rate_limit
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.services.external_transfer_provider_workflow import (
    apply_provider_status_update,
    reconcile_external_transfer_providers,
)

router = APIRouter(prefix="/providers/ihela", tags=["Providers - iHela"])


def _extract_webhook_fields(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    provider_ref = str(
        payload.get("provider_ref")
        or payload.get("provider_reference")
        or payload.get("transaction_id")
        or payload.get("id")
        or ""
    ).strip() or None
    provider_status = str(
        payload.get("status")
        or payload.get("state")
        or payload.get("payment_status")
        or ""
    ).strip() or None
    transfer_ref = str(
        payload.get("reference")
        or payload.get("client_reference")
        or payload.get("transfer_reference")
        or ""
    ).strip() or None
    return provider_ref, provider_status, transfer_ref


@router.post("/webhook")
async def ihela_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:ihela_webhook", limit=120, window_seconds=60)

    raw_body = await request.body()
    signature_header = str(getattr(settings, "IHELA_WEBHOOK_SIGNATURE_HEADER", "X-IHela-Signature") or "X-IHela-Signature")
    signature = request.headers.get(signature_header)
    secret = str(getattr(settings, "IHELA_WEBHOOK_SECRET", "") or "").strip() or str(getattr(settings, "HMAC_SECRET", "") or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="IHELA_WEBHOOK_SECRET manquant")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload iHela invalide")

    provider_ref, provider_status, transfer_ref = _extract_webhook_fields(payload)
    if not provider_status:
        raise HTTPException(status_code=400, detail="provider_status manquant dans le webhook iHela")

    transfer = None
    if provider_ref:
        transfer = await db.scalar(
            select(ExternalTransfers).where(
                ExternalTransfers.provider == "ihela",
                ExternalTransfers.provider_ref == provider_ref,
            )
        )
    if not transfer and transfer_ref:
        transfer = await db.scalar(
            select(ExternalTransfers).where(
                ExternalTransfers.reference_code == transfer_ref,
            )
        )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert iHela introuvable")

    update = await apply_provider_status_update(
        db,
        transfer=transfer,
        provider_status=provider_status,
        provider_ref=provider_ref,
        last_error=str(payload.get("error") or payload.get("message") or "").strip() or None,
        provider_payload=payload,
    )
    await db.commit()
    return {
        "status": "ok",
        "transfer_id": str(transfer.transfer_id),
        "provider_status": update.get("provider_status"),
        "transfer_status": update.get("transfer_status"),
    }


@router.post("/reconcile")
async def ihela_reconcile_now(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if str(getattr(current_user, "role", "") or "").lower() not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Acces refuse")

    summary = await reconcile_external_transfer_providers()
    return {"status": "ok", "summary": summary}
