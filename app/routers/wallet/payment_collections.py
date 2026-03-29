import json

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.users import Users
from app.schemas.payments import (
    MobileMoneyDepositIntentCreate,
    PaymentIntentRead,
    PaymentWebhookResult,
)
from app.services.payments_service import (
    create_mobile_money_deposit_intent,
    list_payment_intents,
    process_mobile_money_provider_webhook,
)

router = APIRouter(prefix="/wallet/payments", tags=["Wallet Payments Collections"])


@router.post("/deposit-intents/mobile-money", response_model=PaymentIntentRead)
async def create_mobile_money_deposit(
    payload: MobileMoneyDepositIntentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await create_mobile_money_deposit_intent(
        db,
        current_user=current_user,
        amount=payload.amount,
        currency_code=payload.currency_code,
        provider_code=payload.provider_code,
        provider_channel=payload.provider_channel,
        payer_identifier=payload.payer_identifier,
        note=payload.note,
    )


@router.get("/intents", response_model=list[PaymentIntentRead])
async def get_payment_intents(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await list_payment_intents(db, user_id=current_user.user_id, limit=limit)


@router.post("/webhooks/mobile-money/{provider_code}", response_model=PaymentWebhookResult)
async def mobile_money_collection_webhook(
    provider_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    intent, credited = await process_mobile_money_provider_webhook(
        db,
        provider_code=provider_code,
        payload=payload,
        raw_body=raw_body,
        signature=x_signature,
    )
    return PaymentWebhookResult(
        status=str(intent.status),
        merchant_reference=str(intent.merchant_reference),
        credited=credited,
        intent_id=intent.intent_id,
    )
