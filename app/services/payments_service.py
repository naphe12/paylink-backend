from __future__ import annotations

import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.payment_events import PaymentEvents
from app.models.payment_intents import (
    PaymentIntentDirection,
    PaymentIntentRail,
    PaymentIntents,
    PaymentIntentStatus,
)
from app.models.wallets import Wallets
from app.schemas.payments import MobileMoneyWebhookPayload
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement


MOBILE_MONEY_PROVIDER_LUMICASH = "lumicash_aggregator"
MOBILE_MONEY_PROVIDER_ECOCASH = "ecocash_aggregator"
MOBILE_MONEY_PROVIDER_ENOTI = "enoti_aggregator"


@dataclass(slots=True)
class NormalizedProviderEvent:
    merchant_reference: str
    provider_reference: str | None
    external_event_id: str | None
    event_type: str | None
    status: str
    amount: Decimal
    currency_code: str
    payer_identifier: str | None
    reason_code: str | None
    raw_payload: dict


@dataclass(slots=True)
class ProviderCollectionInitResult:
    success: bool
    status: str
    reason_code: str | None
    provider_reference: str | None
    response_payload: dict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _payment_reference(prefix: str = "PMT") -> str:
    raw = uuid.uuid4().hex.upper()
    return f"{prefix}-{raw[:12]}"


def _verify_provider_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = str(getattr(settings, "PAYMENTS_MOBILE_MONEY_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        return True
    if not signature:
        return False
    digest = hmac.new(secret.encode(), raw_body, "sha256").hexdigest()
    return hmac.compare_digest(digest, signature.strip())


def _provider_base_url(provider_code: str) -> str:
    if provider_code == MOBILE_MONEY_PROVIDER_LUMICASH:
        return str(getattr(settings, "PAYMENTS_LUMICASH_API_BASE_URL", "") or "").strip()
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        return str(getattr(settings, "PAYMENTS_ECOCASH_API_BASE_URL", "") or "").strip()
    if provider_code == MOBILE_MONEY_PROVIDER_ENOTI:
        return str(getattr(settings, "PAYMENTS_ENOTI_API_BASE_URL", "") or "").strip()
    return ""


def _provider_api_key(provider_code: str) -> str:
    if provider_code == MOBILE_MONEY_PROVIDER_LUMICASH:
        return str(getattr(settings, "PAYMENTS_LUMICASH_API_KEY", "") or "").strip()
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        return str(getattr(settings, "PAYMENTS_ECOCASH_API_KEY", "") or "").strip()
    if provider_code == MOBILE_MONEY_PROVIDER_ENOTI:
        return str(getattr(settings, "PAYMENTS_ENOTI_API_KEY", "") or "").strip()
    return ""


def _provider_collections_path(provider_code: str) -> str:
    if provider_code == MOBILE_MONEY_PROVIDER_LUMICASH:
        return str(getattr(settings, "PAYMENTS_LUMICASH_COLLECTIONS_PATH", "") or "").strip() or "/collections/mobile-money"
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        return str(getattr(settings, "PAYMENTS_ECOCASH_COLLECTIONS_PATH", "") or "").strip() or "/collections/mobile-money"
    if provider_code == MOBILE_MONEY_PROVIDER_ENOTI:
        return str(getattr(settings, "PAYMENTS_ENOTI_COLLECTIONS_PATH", "") or "").strip() or "/collections/mobile-money"
    return "/collections/mobile-money"


def _lumicash_target_instructions(amount: Decimal, merchant_reference: str) -> dict:
    return {
        "mode": "merchant_push_reference",
        "provider_channel": "Lumicash",
        "merchant_name": str(getattr(settings, "PAYMENTS_LUMICASH_MERCHANT_NAME", "") or "").strip(),
        "merchant_number": str(getattr(settings, "PAYMENTS_LUMICASH_MERCHANT_NUMBER", "") or "").strip(),
        "reference": merchant_reference,
        "amount": str(amount),
        "currency_code": "BIF",
        "message": (
            f"Envoyez {amount} BIF via Lumicash au numero marchand configure "
            f"en utilisant la reference {merchant_reference}."
        ),
    }


def _ecocash_target_instructions(amount: Decimal, merchant_reference: str) -> dict:
    return {
        "mode": "merchant_push_reference",
        "provider_channel": "Ecocash",
        "merchant_name": str(getattr(settings, "PAYMENTS_ECOCASH_MERCHANT_NAME", "") or "").strip(),
        "merchant_number": str(getattr(settings, "PAYMENTS_ECOCASH_MERCHANT_NUMBER", "") or "").strip(),
        "reference": merchant_reference,
        "amount": str(amount),
        "currency_code": "BIF",
        "message": (
            f"Envoyez {amount} BIF via Ecocash au numero marchand configure "
            f"en utilisant la reference {merchant_reference}."
        ),
    }


def _enoti_target_instructions(amount: Decimal, merchant_reference: str) -> dict:
    return {
        "mode": "merchant_push_reference",
        "provider_channel": "eNoti",
        "merchant_name": str(getattr(settings, "PAYMENTS_ENOTI_MERCHANT_NAME", "") or "").strip(),
        "merchant_number": str(getattr(settings, "PAYMENTS_ENOTI_MERCHANT_NUMBER", "") or "").strip(),
        "reference": merchant_reference,
        "amount": str(amount),
        "currency_code": "BIF",
        "message": (
            f"Envoyez {amount} BIF via eNoti au compte marchand configure "
            f"en utilisant la reference {merchant_reference}."
        ),
    }


def _build_mobile_money_target_instructions(
    provider_code: str,
    provider_channel: str,
    amount: Decimal,
    merchant_reference: str,
) -> dict:
    if provider_code == MOBILE_MONEY_PROVIDER_LUMICASH:
        return _lumicash_target_instructions(amount, merchant_reference)
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        return _ecocash_target_instructions(amount, merchant_reference)
    if provider_code == MOBILE_MONEY_PROVIDER_ENOTI:
        return _enoti_target_instructions(amount, merchant_reference)
    return {
        "mode": "merchant_push_reference",
        "provider_channel": provider_channel,
        "reference": merchant_reference,
        "amount": str(amount),
        "currency_code": "BIF",
        "message": f"Envoyez {amount} BIF via {provider_channel} avec la reference {merchant_reference}.",
    }


def _map_generic_provider_status(raw_status: str) -> str:
    status = str(raw_status or "").strip().lower()
    if status in {"success", "successful", "paid", "completed"}:
        return "settled"
    if status in {"pending", "processing"}:
        return "pending_provider"
    if status in {"failed", "cancelled", "canceled"}:
        return "failed"
    return status or "pending_provider"


def _map_ecocash_status(raw_status: str, payload: dict) -> str:
    status = str(raw_status or "").strip().lower()
    provider_result = str(payload.get("result_code") or payload.get("result") or "").strip().lower()
    if status in {"successful", "success", "paid", "completed", "complete", "settled"}:
        return "settled"
    if status in {"queued", "initiated", "submitted", "authorised", "authorized", "pending", "processing", "in_progress"}:
        return "pending_provider"
    if status in {"failed", "cancelled", "canceled", "declined", "rejected", "expired", "timeout", "timed_out", "reversed"}:
        return "failed"
    if provider_result in {"0", "success", "successful", "ok"}:
        return "settled"
    if provider_result in {"pending", "processing", "queued"}:
        return "pending_provider"
    if provider_result in {"failed", "error", "timeout", "expired", "reversed"}:
        return "failed"
    return "pending_provider"


def _derive_reason_code(provider_code: str, normalized_status: str, payload: dict) -> str | None:
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        result_code = str(payload.get("result_code") or payload.get("result") or "").strip()
        if result_code:
            return f"ecocash_result:{result_code.lower()}"
    raw_reason = (
        payload.get("reason_code")
        or payload.get("error_code")
        or payload.get("failure_code")
        or payload.get("status_reason")
        or payload.get("reason")
    )
    reason = str(raw_reason or "").strip()
    if reason:
        return reason.lower().replace(" ", "_")
    if normalized_status == PaymentIntentStatus.SETTLED.value:
        return "provider_confirmed"
    if normalized_status == PaymentIntentStatus.FAILED.value:
        return "provider_failed"
    if normalized_status == PaymentIntentStatus.PENDING_PROVIDER.value:
        return "provider_pending"
    return None


def _normalize_webhook_payload(payload: dict, provider_code: str | None = None) -> MobileMoneyWebhookPayload:
    merchant_reference = payload.get("merchant_reference") or payload.get("reference") or payload.get("external_ref")
    provider_reference = payload.get("provider_reference") or payload.get("transaction_id") or payload.get("tx_ref")
    event_id = payload.get("event_id") or payload.get("id")
    event_type = payload.get("event_type") or payload.get("type") or "payment_update"
    raw_status = str(payload.get("status") or payload.get("payment_status") or payload.get("state") or "").strip().lower()
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        status = _map_ecocash_status(raw_status, payload)
    else:
        status = _map_generic_provider_status(raw_status)
    reason_code = _derive_reason_code(str(provider_code or ""), status, payload)
    return MobileMoneyWebhookPayload(
        event_id=str(event_id) if event_id is not None else None,
        event_type=str(event_type) if event_type is not None else None,
        merchant_reference=str(merchant_reference) if merchant_reference is not None else None,
        provider_reference=str(provider_reference) if provider_reference is not None else None,
        status=status,
        amount=Decimal(str(payload.get("amount") or "0")),
        currency_code=str(payload.get("currency_code") or payload.get("currency") or "BIF").upper(),
        payer_identifier=payload.get("payer_identifier") or payload.get("msisdn") or payload.get("phone_number"),
        raw_payload={**dict(payload or {}), "_reason_code": reason_code},
    )


async def _initiate_provider_collection(
    *,
    provider_code: str,
    provider_channel: str,
    amount: Decimal,
    currency_code: str,
    merchant_reference: str,
    payer_identifier: str | None,
) -> ProviderCollectionInitResult:
    base_url = _provider_base_url(provider_code)
    if not base_url:
        return ProviderCollectionInitResult(
            success=False,
            status=PaymentIntentStatus.CREATED.value,
            reason_code="provider_api_not_configured",
            provider_reference=None,
            response_payload={},
        )

    url = f"{base_url.rstrip('/')}/{_provider_collections_path(provider_code).lstrip('/')}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = _provider_api_key(provider_code)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "merchant_reference": merchant_reference,
        "provider_channel": provider_channel,
        "amount": str(amount),
        "currency_code": currency_code,
        "payer_identifier": _normalize_text(payer_identifier) or None,
    }
    try:
        async with httpx.AsyncClient(timeout=float(getattr(settings, "PAYMENTS_PROVIDER_REQUEST_TIMEOUT_SECONDS", 12.0) or 12.0)) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json() if response.content else {}
    except httpx.TimeoutException:
        return ProviderCollectionInitResult(False, PaymentIntentStatus.CREATED.value, "provider_timeout", None, {"url": url})
    except (httpx.HTTPError, ValueError) as exc:
        return ProviderCollectionInitResult(False, PaymentIntentStatus.CREATED.value, "provider_init_error", None, {"url": url, "error": str(exc)})

    raw_status = str(data.get("status") or data.get("payment_status") or data.get("state") or "pending").strip().lower()
    if provider_code == MOBILE_MONEY_PROVIDER_ECOCASH:
        normalized_status = _map_ecocash_status(raw_status, data)
    else:
        normalized_status = _map_generic_provider_status(raw_status)
    provider_reference = data.get("provider_reference") or data.get("transaction_id") or data.get("tx_ref") or data.get("collection_id")
    return ProviderCollectionInitResult(
        success=True,
        status=normalized_status if normalized_status in {
            PaymentIntentStatus.PENDING_PROVIDER.value,
            PaymentIntentStatus.SETTLED.value,
            PaymentIntentStatus.FAILED.value,
        } else PaymentIntentStatus.PENDING_PROVIDER.value,
        reason_code=_derive_reason_code(provider_code, normalized_status, data) or "provider_init_ok",
        provider_reference=str(provider_reference) if provider_reference is not None else None,
        response_payload=dict(data or {}),
    )


async def _primary_wallet(db: AsyncSession, user_id) -> Wallets | None:
    stmt: Select[tuple[Wallets]] = select(Wallets).where(Wallets.user_id == user_id).limit(1)
    return await db.scalar(stmt)


async def create_mobile_money_deposit_intent(
    db: AsyncSession,
    *,
    current_user,
    amount: Decimal,
    currency_code: str,
    provider_code: str,
    provider_channel: str,
    payer_identifier: str | None,
    note: str | None,
) -> PaymentIntents:
    wallet = await _primary_wallet(db, current_user.user_id)
    if wallet is None:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable.")

    normalized_amount = Decimal(amount)
    if normalized_amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")

    normalized_currency = str(currency_code or "BIF").upper()
    merchant_reference = _payment_reference()
    target_instructions = _build_mobile_money_target_instructions(
        provider_code=provider_code,
        provider_channel=provider_channel,
        amount=normalized_amount,
        merchant_reference=merchant_reference,
    )
    intent = PaymentIntents(
        user_id=current_user.user_id,
        wallet_id=wallet.wallet_id,
        direction=PaymentIntentDirection.DEPOSIT,
        rail=PaymentIntentRail.MOBILE_MONEY,
        status=PaymentIntentStatus.CREATED,
        provider_code=provider_code,
        provider_channel=provider_channel,
        amount=normalized_amount,
        currency_code=normalized_currency,
        merchant_reference=merchant_reference,
        payer_identifier=_normalize_text(payer_identifier) or None,
        target_instructions=target_instructions,
        metadata_={
            "source": "wallet_mobile_money_deposit",
            "note": _normalize_text(note) or None,
        },
        expires_at=_utcnow() + timedelta(hours=24),
    )
    db.add(intent)
    await db.flush()
    init_result = await _initiate_provider_collection(
        provider_code=provider_code,
        provider_channel=provider_channel,
        amount=normalized_amount,
        currency_code=normalized_currency,
        merchant_reference=merchant_reference,
        payer_identifier=payer_identifier,
    )
    metadata = dict(intent.metadata_ or {})
    metadata["collection_init"] = {
        "success": init_result.success,
        "status": init_result.status,
        "reason_code": init_result.reason_code,
        "response_payload": init_result.response_payload,
    }
    intent.metadata_ = metadata
    if init_result.provider_reference:
        intent.provider_reference = init_result.provider_reference
    if init_result.success:
        if init_result.status == PaymentIntentStatus.SETTLED.value:
            intent.status = PaymentIntentStatus.SETTLED
            intent.settled_at = _utcnow()
        elif init_result.status == PaymentIntentStatus.FAILED.value:
            intent.status = PaymentIntentStatus.FAILED
        else:
            intent.status = PaymentIntentStatus.PENDING_PROVIDER

    db.add(
        PaymentEvents(
            intent_id=intent.intent_id,
            provider_code=provider_code,
            provider_event_type="collection_init",
            external_event_id=None,
            provider_reference=init_result.provider_reference,
            status=init_result.status,
            reason_code=init_result.reason_code,
            payload=init_result.response_payload or {},
        )
    )
    if intent.status == PaymentIntentStatus.SETTLED:
        await _credit_deposit_intent(db, intent)
    await db.commit()
    await db.refresh(intent)
    return intent


async def list_payment_intents(
    db: AsyncSession,
    *,
    user_id,
    limit: int = 50,
) -> list[PaymentIntents]:
    stmt = (
        select(PaymentIntents)
        .where(PaymentIntents.user_id == user_id)
        .order_by(PaymentIntents.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _credit_deposit_intent(db: AsyncSession, intent: PaymentIntents) -> bool:
    if intent.direction != PaymentIntentDirection.DEPOSIT:
        return False
    if intent.status == PaymentIntentStatus.CREDITED:
        return False

    wallet = await db.get(Wallets, intent.wallet_id)
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet du paiement introuvable.")

    amount = Decimal(intent.amount or 0)
    wallet.available = Decimal(wallet.available or 0) + amount

    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=intent.user_id,
        amount=amount,
        direction="credit",
        operation_type="payment_intent_deposit_credit",
        reference=intent.merchant_reference,
        description=f"Depot mobile money {intent.provider_channel or intent.provider_code}",
    )
    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in_account = await ledger.get_cash_in_account(wallet.currency_code)
    await ledger.post_journal(
        tx_id=None,
        description="Credit automatique depot mobile money",
        metadata={
            "operation": "payment_intent_deposit_credit",
            "intent_id": str(intent.intent_id),
            "merchant_reference": intent.merchant_reference,
            "provider_code": intent.provider_code,
            "provider_reference": intent.provider_reference,
            "wallet_id": str(wallet.wallet_id),
            "user_id": str(intent.user_id),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(
                account=cash_in_account,
                direction="debit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
            LedgerLine(
                account=wallet_account,
                direction="credit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
        ],
    )
    intent.status = PaymentIntentStatus.CREDITED
    intent.credited_at = _utcnow()
    return True


async def process_mobile_money_provider_webhook(
    db: AsyncSession,
    *,
    provider_code: str,
    payload: dict,
    raw_body: bytes,
    signature: str | None,
) -> tuple[PaymentIntents, bool]:
    if not _verify_provider_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Signature webhook invalide.")

    normalized = _normalize_webhook_payload(payload, provider_code=provider_code)
    merchant_reference = _normalize_text(normalized.merchant_reference)
    if not merchant_reference:
        raise HTTPException(status_code=400, detail="merchant_reference manquant.")
    if normalized.amount <= 0:
        raise HTTPException(status_code=400, detail="amount invalide.")

    intent = await db.scalar(
        select(PaymentIntents).where(
            PaymentIntents.provider_code == provider_code,
            PaymentIntents.merchant_reference == merchant_reference,
        )
    )
    if intent is None:
        raise HTTPException(status_code=404, detail="Intent de paiement introuvable.")

    duplicate = await db.scalar(
        select(PaymentEvents).where(
            PaymentEvents.provider_code == provider_code,
            PaymentEvents.external_event_id == normalized.event_id,
        )
    ) if normalized.event_id else None
    if duplicate is not None:
        return intent, intent.status == PaymentIntentStatus.CREDITED

    db.add(
        PaymentEvents(
            intent_id=intent.intent_id,
            provider_code=provider_code,
            provider_event_type=normalized.event_type,
            external_event_id=normalized.event_id,
            provider_reference=normalized.provider_reference,
            status=normalized.status,
            reason_code=normalized.raw_payload.get("_reason_code"),
            payload=normalized.raw_payload,
        )
    )

    intent.provider_reference = normalized.provider_reference or intent.provider_reference
    intent.payer_identifier = _normalize_text(normalized.payer_identifier) or intent.payer_identifier
    metadata = dict(intent.metadata_ or {})
    metadata["last_provider_payload"] = normalized.raw_payload
    metadata["last_provider_reason_code"] = normalized.raw_payload.get("_reason_code")
    intent.metadata_ = metadata

    credited = False
    if normalized.status == PaymentIntentStatus.SETTLED.value:
        intent.status = PaymentIntentStatus.SETTLED
        intent.settled_at = intent.settled_at or _utcnow()
        if Decimal(intent.amount or 0) != Decimal(normalized.amount):
            raise HTTPException(status_code=409, detail="Montant webhook different de l'intent.")
        if str(intent.currency_code or "").upper() != str(normalized.currency_code or "").upper():
            raise HTTPException(status_code=409, detail="Devise webhook differente de l'intent.")
        credited = await _credit_deposit_intent(db, intent)
    elif normalized.status == PaymentIntentStatus.FAILED.value:
        intent.status = PaymentIntentStatus.FAILED
    else:
        intent.status = PaymentIntentStatus.PENDING_PROVIDER

    await db.commit()
    await db.refresh(intent)
    return intent, credited


def dump_provider_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


async def admin_reconcile_payment_intent(
    db: AsyncSession,
    *,
    intent_id,
    admin_user_id,
    provider_reference: str | None = None,
    note: str | None = None,
) -> PaymentIntents:
    intent = await db.get(PaymentIntents, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="Intent de paiement introuvable.")
    if intent.direction != PaymentIntentDirection.DEPOSIT or intent.rail != PaymentIntentRail.MOBILE_MONEY:
        raise HTTPException(status_code=400, detail="Seuls les depots mobile money sont reconciliables ici.")
    if intent.status == PaymentIntentStatus.FAILED:
        raise HTTPException(status_code=409, detail="Intent marque en echec, reconciliation manuelle refusee.")

    normalized_reference = _normalize_text(provider_reference) or intent.provider_reference
    normalized_note = _normalize_text(note) or None

    metadata = dict(intent.metadata_ or {})
    metadata["manual_reconciliation"] = {
        "admin_user_id": str(admin_user_id),
        "provider_reference": normalized_reference,
        "note": normalized_note,
        "reconciled_at": _utcnow().isoformat(),
    }
    intent.metadata_ = metadata
    intent.provider_reference = normalized_reference
    intent.settled_at = intent.settled_at or _utcnow()
    if intent.status != PaymentIntentStatus.CREDITED:
        intent.status = PaymentIntentStatus.SETTLED

    db.add(
        PaymentEvents(
            intent_id=intent.intent_id,
            provider_code=intent.provider_code,
            provider_event_type="manual_reconcile",
            external_event_id=None,
            provider_reference=normalized_reference,
            status="settled_manual",
            reason_code="manual_reconciliation",
            payload={
                "source": "admin_manual_reconciliation",
                "note": normalized_note,
                "admin_user_id": str(admin_user_id),
                "merchant_reference": intent.merchant_reference,
            },
        )
    )

    if intent.status != PaymentIntentStatus.CREDITED:
        await _credit_deposit_intent(db, intent)

    await db.commit()
    await db.refresh(intent)
    return intent


async def admin_update_payment_intent_status(
    db: AsyncSession,
    *,
    intent_id,
    admin_user_id,
    action: str,
    note: str | None = None,
) -> PaymentIntents:
    intent = await db.get(PaymentIntents, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="Intent de paiement introuvable.")
    if intent.direction != PaymentIntentDirection.DEPOSIT or intent.rail != PaymentIntentRail.MOBILE_MONEY:
        raise HTTPException(status_code=400, detail="Seuls les depots mobile money sont modifiables ici.")
    if intent.status == PaymentIntentStatus.CREDITED:
        raise HTTPException(status_code=409, detail="Intent deja credite.")

    normalized_action = _normalize_text(action).lower()
    normalized_note = _normalize_text(note) or None

    if normalized_action == "reopen_failed":
        if intent.status != PaymentIntentStatus.FAILED:
            raise HTTPException(status_code=409, detail="Seuls les intents failed peuvent etre reouverts.")
        intent.status = PaymentIntentStatus.CREATED
    elif normalized_action == "retry_waiting":
        if intent.status == PaymentIntentStatus.FAILED:
            raise HTTPException(status_code=409, detail="Utilisez reopen_failed pour un intent failed.")
        intent.status = PaymentIntentStatus.PENDING_PROVIDER
    else:
        raise HTTPException(status_code=400, detail="Action de statut non prise en charge.")

    metadata = dict(intent.metadata_ or {})
    metadata["admin_status_action"] = {
        "action": normalized_action,
        "admin_user_id": str(admin_user_id),
        "note": normalized_note,
        "applied_at": _utcnow().isoformat(),
    }
    intent.metadata_ = metadata

    db.add(
        PaymentEvents(
            intent_id=intent.intent_id,
            provider_code=intent.provider_code,
            provider_event_type=normalized_action,
            external_event_id=None,
            provider_reference=intent.provider_reference,
            status=str(intent.status),
            reason_code=normalized_action,
            payload={
                "source": "admin_status_action",
                "action": normalized_action,
                "note": normalized_note,
                "admin_user_id": str(admin_user_id),
                "merchant_reference": intent.merchant_reference,
            },
        )
    )

    await db.commit()
    await db.refresh(intent)
    return intent
