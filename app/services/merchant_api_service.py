from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_accounts import BusinessAccounts
from app.models.business_members import BusinessMembers
from app.models.merchant_api_keys import MerchantApiKeys
from app.models.merchant_webhook_events import MerchantWebhookEvents
from app.models.merchant_webhooks import MerchantWebhooks
from app.models.users import Users

WRITE_ROLES = {"owner", "admin"}
READ_ROLES = {"owner", "admin", "cashier", "viewer"}
ALLOWED_WEBHOOK_STATUSES = {"active", "paused", "revoked"}
DEFAULT_EVENT_TYPES = ["payment.request.paid", "payment.request.expired", "wallet.balance.updated"]
WEBHOOK_RETRY_DELAYS_MINUTES = (5, 15, 60)
WEBHOOK_TIMEOUT_SECONDS = 10


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _require_business_membership(
    db: AsyncSession,
    *,
    business_id: UUID,
    current_user: Users,
    write: bool,
) -> tuple[BusinessAccounts, BusinessMembers]:
    business = await db.get(BusinessAccounts, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Compte business introuvable")

    membership = await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.user_id == current_user.user_id,
            BusinessMembers.status == "active",
        )
    )
    if not membership or membership.role not in (WRITE_ROLES if write else READ_ROLES):
        raise HTTPException(status_code=403, detail="Acces business insuffisant")
    return business, membership


def _serialize_key(item: MerchantApiKeys, *, plain_api_key: str | None = None) -> dict:
    return {
        "key_id": item.key_id,
        "business_id": item.business_id,
        "key_name": item.key_name,
        "key_prefix": item.key_prefix,
        "is_active": bool(item.is_active and item.revoked_at is None),
        "last_used_at": item.last_used_at,
        "revoked_at": item.revoked_at,
        "metadata": dict(item.metadata_ or {}),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "plain_api_key": plain_api_key,
    }


def _serialize_webhook(item: MerchantWebhooks, *, plain_signing_secret: str | None = None) -> dict:
    return {
        "webhook_id": item.webhook_id,
        "business_id": item.business_id,
        "target_url": item.target_url,
        "status": item.status,
        "event_types": list(item.event_types or []),
        "is_active": bool(item.is_active and item.revoked_at is None and item.status != "revoked"),
        "last_tested_at": item.last_tested_at,
        "revoked_at": item.revoked_at,
        "metadata": dict(item.metadata_ or {}),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "plain_signing_secret": plain_signing_secret,
    }


def _serialize_event(item: MerchantWebhookEvents) -> dict:
    return {
        "event_id": item.event_id,
        "webhook_id": item.webhook_id,
        "business_id": item.business_id,
        "event_type": item.event_type,
        "delivery_status": item.delivery_status,
        "response_status_code": item.response_status_code,
        "request_signature": item.request_signature,
        "payload": dict(item.payload or {}),
        "response_body": item.response_body,
        "attempt_count": int(item.attempt_count or 0),
        "last_attempted_at": item.last_attempted_at,
        "next_retry_at": item.next_retry_at,
        "delivered_at": item.delivered_at,
        "metadata": dict(item.metadata_ or {}),
        "created_at": item.created_at,
    }


def _canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _build_signature(webhook: MerchantWebhooks, payload: dict) -> str:
    signing_key = (webhook.signing_secret_hash or "").encode("utf-8")
    message = _canonical_payload(payload).encode("utf-8")
    return hmac.new(signing_key, message, hashlib.sha256).hexdigest()


def _next_retry_after(attempt_count: int, *, now: datetime) -> datetime | None:
    if attempt_count <= 0:
        return now + timedelta(minutes=WEBHOOK_RETRY_DELAYS_MINUTES[0])
    index = min(attempt_count - 1, len(WEBHOOK_RETRY_DELAYS_MINUTES) - 1)
    if index >= len(WEBHOOK_RETRY_DELAYS_MINUTES):
        return None
    if attempt_count > len(WEBHOOK_RETRY_DELAYS_MINUTES):
        return None
    return now + timedelta(minutes=WEBHOOK_RETRY_DELAYS_MINUTES[index])


async def _deliver_event(
    db: AsyncSession,
    *,
    webhook: MerchantWebhooks,
    event_type: str,
    payload: dict,
    existing_event: MerchantWebhookEvents | None = None,
    mode: str,
) -> MerchantWebhookEvents:
    now = datetime.now(timezone.utc)
    signature = _build_signature(webhook, payload)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "PesaPaid-Merchant-Webhooks/1.0",
        "X-PesaPaid-Event": event_type,
        "X-PesaPaid-Webhook-Id": str(webhook.webhook_id),
        "X-PesaPaid-Business-Id": str(webhook.business_id),
        "X-PesaPaid-Signature": signature,
    }
    event = existing_event or MerchantWebhookEvents(
        webhook_id=webhook.webhook_id,
        business_id=webhook.business_id,
        event_type=event_type,
        payload=payload,
    )
    if existing_event is None:
        db.add(event)

    event.event_type = event_type
    event.payload = payload
    event.request_signature = signature
    event.attempt_count = int(event.attempt_count or 0) + 1
    event.last_attempted_at = now
    event.metadata_ = {
        **dict(event.metadata_ or {}),
        "mode": mode,
        "target_url": webhook.target_url,
        "headers": headers,
    }

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook.target_url, json=payload, headers=headers)
        event.response_status_code = response.status_code
        event.response_body = (response.text or "")[:2000] or None
        if 200 <= response.status_code < 300:
            event.delivery_status = "delivered"
            event.delivered_at = now
            event.next_retry_at = None
        else:
            event.delivery_status = "failed"
            event.delivered_at = None
            event.next_retry_at = _next_retry_after(event.attempt_count, now=now)
    except httpx.HTTPError as exc:
        event.delivery_status = "failed"
        event.response_status_code = None
        event.response_body = str(exc)[:2000]
        event.delivered_at = None
        event.next_retry_at = _next_retry_after(event.attempt_count, now=now)

    webhook.last_tested_at = now
    webhook.updated_at = now
    await db.commit()
    await db.refresh(event)
    return event


async def list_business_integrations(db: AsyncSession, *, business_id: UUID, current_user: Users) -> dict:
    business, membership = await _require_business_membership(
        db,
        business_id=business_id,
        current_user=current_user,
        write=False,
    )
    keys = (
        await db.execute(
            select(MerchantApiKeys)
            .where(MerchantApiKeys.business_id == business_id)
            .order_by(MerchantApiKeys.created_at.desc())
        )
    ).scalars().all()
    webhooks = (
        await db.execute(
            select(MerchantWebhooks)
            .where(MerchantWebhooks.business_id == business_id)
            .order_by(MerchantWebhooks.created_at.desc())
        )
    ).scalars().all()
    events = (
        await db.execute(
            select(MerchantWebhookEvents)
            .where(MerchantWebhookEvents.business_id == business_id)
            .order_by(MerchantWebhookEvents.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return {
        "business_id": business.business_id,
        "business_label": business.display_name or business.legal_name,
        "membership_role": membership.role,
        "api_keys": [_serialize_key(item) for item in keys],
        "webhooks": [_serialize_webhook(item) for item in webhooks],
        "recent_events": [_serialize_event(item) for item in events],
    }


async def create_business_api_key(db: AsyncSession, *, business_id: UUID, current_user: Users, payload) -> dict:
    await _require_business_membership(db, business_id=business_id, current_user=current_user, write=True)
    plain_api_key = f"pk_live_{secrets.token_urlsafe(24)}"
    item = MerchantApiKeys(
        business_id=business_id,
        created_by_user_id=current_user.user_id,
        key_name=payload.key_name.strip(),
        key_prefix=plain_api_key[:18],
        key_hash=_hash_secret(plain_api_key),
        metadata_={"last4": plain_api_key[-4:]},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_key(item, plain_api_key=plain_api_key)


async def revoke_business_api_key(db: AsyncSession, *, key_id: UUID, current_user: Users) -> dict:
    item = await db.get(MerchantApiKeys, key_id)
    if not item:
        raise HTTPException(status_code=404, detail="Cle API introuvable")
    await _require_business_membership(db, business_id=item.business_id, current_user=current_user, write=True)
    item.is_active = False
    item.revoked_at = datetime.now(timezone.utc)
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _serialize_key(item)


async def create_business_webhook(db: AsyncSession, *, business_id: UUID, current_user: Users, payload) -> dict:
    await _require_business_membership(db, business_id=business_id, current_user=current_user, write=True)
    plain_signing_secret = f"whsec_{secrets.token_urlsafe(24)}"
    event_types = [str(item).strip() for item in (payload.event_types or []) if str(item).strip()]
    item = MerchantWebhooks(
        business_id=business_id,
        created_by_user_id=current_user.user_id,
        target_url=str(payload.target_url),
        status="active",
        event_types=event_types or DEFAULT_EVENT_TYPES,
        signing_secret_hash=_hash_secret(plain_signing_secret),
        metadata_={"last4": plain_signing_secret[-4:]},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_webhook(item, plain_signing_secret=plain_signing_secret)


async def update_business_webhook_status(db: AsyncSession, *, webhook_id: UUID, current_user: Users, payload) -> dict:
    item = await db.get(MerchantWebhooks, webhook_id)
    if not item:
        raise HTTPException(status_code=404, detail="Webhook marchand introuvable")
    await _require_business_membership(db, business_id=item.business_id, current_user=current_user, write=True)
    status = str(payload.status or "").strip().lower()
    if status not in ALLOWED_WEBHOOK_STATUSES:
        raise HTTPException(status_code=400, detail="Statut webhook invalide")
    item.status = status
    item.is_active = status == "active"
    item.revoked_at = datetime.now(timezone.utc) if status == "revoked" else None
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _serialize_webhook(item)


async def send_test_webhook(db: AsyncSession, *, webhook_id: UUID, current_user: Users) -> dict:
    item = await db.get(MerchantWebhooks, webhook_id)
    if not item:
        raise HTTPException(status_code=404, detail="Webhook marchand introuvable")
    await _require_business_membership(db, business_id=item.business_id, current_user=current_user, write=True)
    if item.status == "revoked":
        raise HTTPException(status_code=400, detail="Webhook revoque")

    now = datetime.now(timezone.utc)
    payload = {
        "event": "merchant.webhook.test",
        "business_id": str(item.business_id),
        "webhook_id": str(item.webhook_id),
        "sent_at": now.isoformat(),
    }
    event = await _deliver_event(
        db,
        webhook=item,
        event_type="merchant.webhook.test",
        payload=payload,
        mode="test",
    )
    return _serialize_event(event)


async def retry_webhook_event(db: AsyncSession, *, event_id: UUID, current_user: Users) -> dict:
    event = await db.get(MerchantWebhookEvents, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evenement webhook introuvable")

    webhook = await db.get(MerchantWebhooks, event.webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook marchand introuvable")
    await _require_business_membership(db, business_id=webhook.business_id, current_user=current_user, write=True)
    if webhook.status == "revoked":
        raise HTTPException(status_code=400, detail="Webhook revoque")

    retried = await _deliver_event(
        db,
        webhook=webhook,
        event_type=event.event_type,
        payload=dict(event.payload or {}),
        existing_event=event,
        mode="manual_retry",
    )
    return _serialize_event(retried)


async def retry_due_webhook_events(
    db: AsyncSession,
    *,
    business_id: UUID,
    current_user: Users,
    limit: int = 20,
) -> list[dict]:
    await _require_business_membership(db, business_id=business_id, current_user=current_user, write=True)
    now = datetime.now(timezone.utc)
    due_events = (
        await db.execute(
            select(MerchantWebhookEvents)
            .where(
                MerchantWebhookEvents.business_id == business_id,
                MerchantWebhookEvents.delivery_status == "failed",
                MerchantWebhookEvents.next_retry_at.is_not(None),
                MerchantWebhookEvents.next_retry_at <= now,
            )
            .order_by(MerchantWebhookEvents.next_retry_at.asc(), MerchantWebhookEvents.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    delivered_events: list[dict] = []
    for event in due_events:
        webhook = await db.get(MerchantWebhooks, event.webhook_id)
        if not webhook or webhook.status == "revoked":
            continue
        retried = await _deliver_event(
            db,
            webhook=webhook,
            event_type=event.event_type,
            payload=dict(event.payload or {}),
            existing_event=event,
            mode="scheduled_retry",
        )
        delivered_events.append(_serialize_event(retried))
    return delivered_events
