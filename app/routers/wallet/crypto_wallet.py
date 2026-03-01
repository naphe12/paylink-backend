from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.security.rate_limit import rate_limit
from app.services.wallet_crypto_deposit_service import (
    cancel_wallet_deposit_request,
    create_wallet_deposit_request,
    get_wallet_deposit_instruction,
    list_wallet_deposit_requests,
    normalize_network,
    normalize_wallet_token,
    process_wallet_crypto_webhook,
)
from app.services.wallet_service import (
    ensure_usdc_wallet_account,
    ensure_usdt_wallet_account,
    get_usdc_balance,
    get_usdt_balance,
)

router = APIRouter(prefix="/wallet/crypto", tags=["Wallet Crypto"])


class CreateDepositRequestPayload(BaseModel):
    token_symbol: str = Field(..., min_length=4, max_length=4)
    network: str = Field(default="POLYGON", min_length=3, max_length=32)
    expected_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    ttl_minutes: int = Field(default=30, ge=5, le=240)


class WalletDepositWebhook(BaseModel):
    network: str
    tx_hash: str
    log_index: int = 0
    from_address: str | None = None
    to_address: str
    amount: Decimal
    confirmations: int
    token_symbol: str | None = None
    token_address: str | None = None
    amount_raw: str | None = None
    block_number: int | None = None
    block_timestamp: int | None = None


@router.get("/balances")
async def wallet_crypto_balances(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    user_id = str(current_user.user_id)
    await ensure_usdc_wallet_account(user_id, db=db)
    await ensure_usdt_wallet_account(user_id, db=db)
    usdc_balance = await get_usdc_balance(user_id, db=db)
    usdt_balance = await get_usdt_balance(user_id, db=db)
    return {
        "balances": {
            "USDC": float(usdc_balance),
            "USDT": float(usdt_balance),
        }
    }


@router.get("/deposit-instructions")
async def wallet_crypto_deposit_instructions(
    token_symbol: str = Query(..., min_length=4, max_length=4),
    network: str = Query(default="POLYGON"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_wallet_deposit_instruction(
        db,
        user_id=str(current_user.user_id),
        token_symbol=normalize_wallet_token(token_symbol),
        network=normalize_network(network),
    )


@router.get("/deposit-requests")
async def wallet_crypto_deposit_requests(
    token_symbol: str | None = Query(default=None, min_length=4, max_length=4),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return {
        "items": await list_wallet_deposit_requests(
            db,
            user_id=str(current_user.user_id),
            token_symbol=token_symbol,
        )
    }


@router.post("/deposit-requests")
async def create_crypto_deposit_request(
    payload: CreateDepositRequestPayload,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        result = await create_wallet_deposit_request(
            db,
            user_id=str(current_user.user_id),
            token_symbol=payload.token_symbol,
            network=payload.network,
            expected_amount=payload.expected_amount,
            ttl_minutes=payload.ttl_minutes,
        )
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/deposit-requests/{request_id}/cancel")
async def cancel_crypto_deposit_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        await cancel_wallet_deposit_request(
            db,
            user_id=str(current_user.user_id),
            request_id=request_id,
        )
        await db.commit()
        return {"status": "CANCELLED", "request_id": request_id}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhooks/polygon")
async def wallet_crypto_polygon_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:wallet_crypto_webhook", limit=60, window_seconds=60)

    raw_body = await request.body()
    signature = request.headers.get("X-Paylink-Signature")
    secret = settings.HMAC_SECRET or settings.ESCROW_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = WalletDepositWebhook.model_validate(await request.json())
    token_symbol = payload.token_symbol
    if not token_symbol:
        token_address = str(payload.token_address or "").lower()
        if token_address and token_address == str(settings.USDC_CONTRACT_ADDRESS or "").lower():
            token_symbol = "USDC"
        elif token_address and token_address == str(settings.USDT_CONTRACT_ADDRESS or "").lower():
            token_symbol = "USDT"

    if not token_symbol:
        raise HTTPException(status_code=400, detail="Missing token_symbol")

    try:
        result = await process_wallet_crypto_webhook(
            db,
            token_symbol=token_symbol,
            network=payload.network,
            tx_hash=payload.tx_hash,
            log_index=payload.log_index,
            from_address=payload.from_address,
            to_address=payload.to_address,
            amount=payload.amount,
            confirmations=payload.confirmations,
            metadata=payload.model_dump(mode="json"),
        )
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
