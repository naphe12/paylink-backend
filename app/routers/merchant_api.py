from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.merchant_api import (
    MerchantApiKeyCreate,
    MerchantApiKeyRead,
    MerchantIntegrationSummary,
    MerchantWebhookCreate,
    MerchantWebhookEventRead,
    MerchantWebhookRead,
    MerchantWebhookStatusUpdate,
)
from app.services.merchant_api_service import (
    create_business_api_key,
    create_business_webhook,
    list_business_integrations,
    rotate_webhook_secret,
    retry_due_webhook_events,
    retry_webhook_event,
    revoke_business_api_key,
    send_test_webhook,
    update_business_webhook_status,
)

router = APIRouter(tags=["Merchant API"])


@router.get("/merchant-api/businesses/{business_id}", response_model=MerchantIntegrationSummary)
async def get_business_integrations_route(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_business_integrations(db, business_id=business_id, current_user=current_user)


@router.post("/merchant-api/businesses/{business_id}/keys", response_model=MerchantApiKeyRead)
async def create_business_api_key_route(
    business_id: UUID,
    payload: MerchantApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_business_api_key(db, business_id=business_id, current_user=current_user, payload=payload)


@router.post("/merchant-api/keys/{key_id}/revoke", response_model=MerchantApiKeyRead)
async def revoke_business_api_key_route(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await revoke_business_api_key(db, key_id=key_id, current_user=current_user)


@router.post("/merchant-api/businesses/{business_id}/webhooks", response_model=MerchantWebhookRead)
async def create_business_webhook_route(
    business_id: UUID,
    payload: MerchantWebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_business_webhook(db, business_id=business_id, current_user=current_user, payload=payload)


@router.post("/merchant-api/webhooks/{webhook_id}/status", response_model=MerchantWebhookRead)
async def update_business_webhook_status_route(
    webhook_id: UUID,
    payload: MerchantWebhookStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_business_webhook_status(db, webhook_id=webhook_id, current_user=current_user, payload=payload)


@router.post("/merchant-api/webhooks/{webhook_id}/rotate-secret", response_model=MerchantWebhookRead)
async def rotate_webhook_secret_route(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await rotate_webhook_secret(db, webhook_id=webhook_id, current_user=current_user)


@router.post("/merchant-api/webhooks/{webhook_id}/test", response_model=MerchantWebhookEventRead)
async def send_test_webhook_route(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await send_test_webhook(db, webhook_id=webhook_id, current_user=current_user)


@router.post("/merchant-api/webhook-events/{event_id}/retry", response_model=MerchantWebhookEventRead)
async def retry_webhook_event_route(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await retry_webhook_event(db, event_id=event_id, current_user=current_user)


@router.post("/merchant-api/businesses/{business_id}/webhooks/retry-due", response_model=list[MerchantWebhookEventRead])
async def retry_due_webhook_events_route(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await retry_due_webhook_events(db, business_id=business_id, current_user=current_user)
