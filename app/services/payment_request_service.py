from __future__ import annotations

import hashlib
import hmac
from calendar import monthrange
from datetime import datetime, timezone
from datetime import timedelta
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business_accounts import BusinessAccounts
from app.models.business_members import BusinessMembers
from app.models.payment_request_events import PaymentRequestEvents
from app.models.payment_request_reminders import PaymentRequestReminders
from app.models.payment_requests import PaymentRequests
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.schemas.payment_requests import PaymentRequestAdminRead, PaymentRequestCreate
from app.services.wallet_history import log_wallet_movement
from app.utils.notify import send_notification

BUSINESS_PAYMENT_READ_ROLES = {"owner", "admin", "cashier", "viewer"}
BUSINESS_PAYMENT_WRITE_ROLES = {"owner", "admin", "cashier"}
MANUAL_REMINDER_COOLDOWN = timedelta(hours=6)
BUSINESS_PAYMENT_CHANNEL_ALIASES = {
    "": "business_link",
    "business_link": "business_link",
    "link": "business_link",
    "static_qr": "static_qr",
    "qr_static": "static_qr",
    "dynamic_qr": "dynamic_qr",
    "qr_dynamic": "dynamic_qr",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_identifier(identifier: str) -> tuple[str, str]:
    ident = " ".join(str(identifier or "").strip().split())
    normalized = ident.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    return normalized, paytag


def _share_token(requester_user_id: UUID, amount: Decimal, created_at: datetime) -> str:
    secret = str(getattr(settings, "SECRET_KEY", "") or "pesapaid-payment-request").encode()
    raw = f"{requester_user_id}:{amount}:{created_at.isoformat()}".encode()
    digest = hmac.new(secret, raw, hashlib.sha256).hexdigest().upper()
    return f"PR-{digest[:18]}"


def _build_public_pay_url(share_token: str | None) -> str | None:
    token = str(share_token or "").strip()
    if not token:
        return None
    base = str(getattr(settings, "FRONTEND_URL", "") or "http://localhost:5173").rstrip("/")
    return f"{base}/pay/request/{token}"


def _build_scan_to_pay_payload(request_obj: PaymentRequests) -> dict:
    pay_url = _build_public_pay_url(request_obj.share_token)
    if not pay_url:
        return {}

    mode = "link"
    if request_obj.channel == "static_qr":
        mode = "static"
    elif request_obj.channel == "dynamic_qr":
        mode = "dynamic"

    return {
        "type": "payment_request",
        "mode": mode,
        "share_token": request_obj.share_token,
        "pay_url": pay_url,
        "amount": str(request_obj.amount),
        "currency_code": request_obj.currency_code,
    }


async def _find_user_by_identifier(db: AsyncSession, identifier: str) -> Users | None:
    normalized, paytag = _normalize_identifier(identifier)
    if not normalized:
        return None
    return await db.scalar(
        select(Users).where(
            or_(
                func.lower(Users.email) == normalized,
                func.lower(Users.username) == normalized,
                func.lower(Users.paytag) == paytag,
                Users.phone_e164 == identifier.strip(),
            )
        )
    )


async def _get_user_wallet(db: AsyncSession, user_id: UUID, currency_code: str) -> Wallets | None:
    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == user_id,
            Wallets.currency_code == currency_code,
        )
    )
    if wallet:
        return wallet
    return await db.scalar(select(Wallets).where(Wallets.user_id == user_id).order_by(Wallets.wallet_id.asc()))


async def _append_event(
    db: AsyncSession,
    *,
    request_id: UUID,
    actor_user_id: UUID | None,
    actor_role: str | None,
    event_type: str,
    before_status: str | None,
    after_status: str | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        PaymentRequestEvents(
            request_id=request_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            event_type=event_type,
            before_status=before_status,
            after_status=after_status,
            metadata_=metadata or {},
        )
    )
    await db.flush()


async def _mark_expired_if_needed(db: AsyncSession, request_obj: PaymentRequests) -> bool:
    now = _utcnow()
    if request_obj.status == "pending" and request_obj.expires_at and request_obj.expires_at <= now:
        previous_status = request_obj.status
        request_obj.status = "expired"
        request_obj.updated_at = now
        await _append_event(
            db,
            request_id=request_obj.request_id,
            actor_user_id=None,
            actor_role="system",
            event_type="expired",
            before_status=previous_status,
            after_status=request_obj.status,
            metadata={"reason": "expires_at_reached"},
        )
        await db.flush()
        return True
    return False


def _display_user(user: Users | None) -> str | None:
    if not user:
        return None
    return user.paytag or user.username or user.email or user.full_name


def _role_value(user: Users | None) -> str | None:
    if not user:
        return None
    return getattr(user.role, "value", user.role)


def _requester_label(request_obj: PaymentRequests, requester: Users | None) -> str | None:
    metadata = request_obj.metadata_ or {}
    business_label = str(metadata.get("business_label") or "").strip()
    if business_label:
        return business_label
    return _display_user(requester)


def _extract_recurrence_fields(metadata: dict | None) -> dict:
    payload = metadata or {}
    recurrence = payload.get("recurrence") if isinstance(payload.get("recurrence"), dict) else {}
    auto_pay = payload.get("auto_pay") if isinstance(payload.get("auto_pay"), dict) else {}
    frequency = str(recurrence.get("frequency") or "none").lower().strip()
    if frequency not in {"none", "daily", "weekly", "monthly"}:
        frequency = "none"
    return {
        "recurrence_frequency": frequency,
        "recurrence_count": recurrence.get("count"),
        "recurrence_end_at": recurrence.get("end_at"),
        "auto_pay_enabled": bool(auto_pay.get("enabled") is True),
        "auto_pay_max_amount": auto_pay.get("max_amount"),
    }


def _default_reminder_config() -> dict:
    return {
        "manual_count": 0,
        "next_manual_at": None,
    }


def _extract_reminder_fields(metadata: dict | None, *, now: datetime | None = None) -> dict:
    payload = metadata or {}
    reminder = payload.get("reminder") if isinstance(payload.get("reminder"), dict) else {}
    raw_manual_count = reminder.get("manual_count")
    try:
        manual_count = max(int(raw_manual_count or 0), 0)
    except Exception:
        manual_count = 0
    next_manual_at = _parse_iso_datetime(reminder.get("next_manual_at"))
    current_time = now or _utcnow()
    can_send = next_manual_at is None or next_manual_at <= current_time
    return {
        "manual_reminder_count": manual_count,
        "next_manual_reminder_at": next_manual_at,
        "can_send_manual_reminder": can_send,
    }


def _set_manual_reminder_metadata(metadata: dict | None, *, now: datetime) -> dict:
    payload = dict(metadata or {})
    reminder = payload.get("reminder") if isinstance(payload.get("reminder"), dict) else {}
    raw_manual_count = reminder.get("manual_count")
    try:
        manual_count = max(int(raw_manual_count or 0), 0)
    except Exception:
        manual_count = 0
    manual_count += 1
    next_allowed_at = now + MANUAL_REMINDER_COOLDOWN
    payload["reminder"] = {
        "manual_count": manual_count,
        "next_manual_at": next_allowed_at.isoformat(),
    }
    return payload


def _extract_auto_pay_config(metadata: dict | None) -> tuple[bool, Decimal | None]:
    fields = _extract_recurrence_fields(metadata)
    enabled = bool(fields.get("auto_pay_enabled"))
    raw_limit = fields.get("auto_pay_max_amount")
    if raw_limit in (None, ""):
        return enabled, None
    try:
        return enabled, Decimal(str(raw_limit))
    except Exception:
        return enabled, None


def _parse_iso_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_next_due_at(current_due_at: datetime, *, frequency: str) -> datetime:
    normalized = str(frequency or "").lower().strip()
    if normalized == "daily":
        return current_due_at + timedelta(days=1)
    if normalized == "weekly":
        return current_due_at + timedelta(days=7)
    if normalized == "monthly":
        month = current_due_at.month + 1
        year = current_due_at.year
        if month > 12:
            year += 1
            month = 1
        day = min(current_due_at.day, monthrange(year, month)[1])
        return current_due_at.replace(year=year, month=month, day=day)
    raise ValueError("Unsupported recurrence frequency")


def _compute_next_expires_at(
    *,
    current_due_at: datetime | None,
    current_expires_at: datetime | None,
    next_due_at: datetime,
) -> datetime | None:
    if not current_due_at or not current_expires_at:
        return None
    delta = current_expires_at - current_due_at
    if delta.total_seconds() <= 0:
        return None
    return next_due_at + delta


def _build_recurrence_config(payload: PaymentRequestCreate, *, amount: Decimal) -> dict:
    frequency = str(payload.recurrence_frequency or "none").lower().strip()
    if frequency not in {"none", "daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="Frequence de recurrence invalide.")
    if payload.recurrence_end_at and payload.recurrence_end_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="recurrence_end_at doit contenir un fuseau horaire.")
    if frequency != "none" and not payload.due_at:
        raise HTTPException(status_code=400, detail="due_at est obligatoire pour une demande recurrente.")
    if payload.recurrence_count is not None and frequency == "none":
        raise HTTPException(status_code=400, detail="recurrence_count exige une frequence recurrente.")
    if payload.recurrence_end_at is not None and frequency == "none":
        raise HTTPException(status_code=400, detail="recurrence_end_at exige une frequence recurrente.")

    if payload.auto_pay_enabled is True or payload.auto_pay_max_amount is not None:
        raise HTTPException(
            status_code=400,
            detail="Auto-pay doit etre activee par le payeur depuis la demande recue.",
        )
    return {
        "recurrence": {
            "frequency": frequency,
            "count": payload.recurrence_count,
            "end_at": payload.recurrence_end_at.isoformat() if payload.recurrence_end_at else None,
        },
        "auto_pay": {
            "enabled": False,
            "max_amount": None,
        },
        "reminder": _default_reminder_config(),
    }


async def _users_map(db: AsyncSession, user_ids: Iterable[UUID | None]) -> dict[UUID, Users]:
    valid_ids = [user_id for user_id in user_ids if user_id]
    if not valid_ids:
        return {}
    rows = await db.execute(select(Users).where(Users.user_id.in_(valid_ids)))
    return {item.user_id: item for item in rows.scalars().all()}


def _is_due(request_obj: PaymentRequests, now: datetime | None = None) -> bool:
    current_time = now or _utcnow()
    if request_obj.status != "pending" or not request_obj.due_at:
        return False
    if request_obj.expires_at and request_obj.expires_at <= current_time:
        return False
    return request_obj.due_at <= current_time


def _serialize_request(request_obj: PaymentRequests, *, current_user_id: UUID, users: dict[UUID, Users]) -> dict:
    now = _utcnow()
    requester = users.get(request_obj.requester_user_id)
    payer = users.get(request_obj.payer_user_id) if request_obj.payer_user_id else None
    role = "requester" if request_obj.requester_user_id == current_user_id else "payer"
    requester_label = _requester_label(request_obj, requester)
    counterpart = payer if role == "requester" else requester
    recurrence_fields = _extract_recurrence_fields(request_obj.metadata_ or {})
    reminder_fields = _extract_reminder_fields(request_obj.metadata_ or {}, now=now)
    pay_url = _build_public_pay_url(request_obj.share_token)
    scan_to_pay_payload = _build_scan_to_pay_payload(request_obj)
    return {
        "request_id": request_obj.request_id,
        "requester_user_id": request_obj.requester_user_id,
        "payer_user_id": request_obj.payer_user_id,
        "amount": request_obj.amount,
        "currency_code": request_obj.currency_code,
        "status": request_obj.status,
        "channel": request_obj.channel,
        "title": request_obj.title,
        "note": request_obj.note,
        "share_token": request_obj.share_token,
        "public_pay_url": pay_url,
        "scan_to_pay_payload": scan_to_pay_payload,
        "due_at": request_obj.due_at,
        "expires_at": request_obj.expires_at,
        "paid_at": request_obj.paid_at,
        "declined_at": request_obj.declined_at,
        "cancelled_at": request_obj.cancelled_at,
        "last_reminder_at": request_obj.last_reminder_at,
        "metadata": request_obj.metadata_ or {},
        "created_at": request_obj.created_at,
        "updated_at": request_obj.updated_at,
        "counterpart_label": _display_user(counterpart) if role == "requester" else requester_label,
        "role": role,
        "is_due": _is_due(request_obj, now),
        **recurrence_fields,
        **reminder_fields,
    }


async def _send_due_reminder_if_needed(
    db: AsyncSession,
    *,
    request_obj: PaymentRequests,
    requester_label: str,
) -> bool:
    now = _utcnow()
    if not _is_due(request_obj, now):
        return False
    if not request_obj.payer_user_id:
        return False
    if request_obj.last_reminder_at and request_obj.due_at and request_obj.last_reminder_at >= request_obj.due_at:
        return False

    request_obj.last_reminder_at = now
    request_obj.updated_at = now
    db.add(
        PaymentRequestReminders(
            request_id=request_obj.request_id,
            reminder_type="auto_due",
            status="sent",
            scheduled_for=now,
            sent_at=now,
            metadata_={"reason": "due_at_reached", "mode": "auto_due"},
        )
    )
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=None,
        actor_role="system",
        event_type="reminder_sent",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={"reason": "due_at_reached", "mode": "auto_due"},
    )
    await send_notification(
        str(request_obj.payer_user_id),
        f"Rappel automatique de demande de paiement de {requester_label} ({request_obj.amount} {request_obj.currency_code}).",
    )
    await db.flush()
    return True


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
    if not bool(business.is_active):
        raise HTTPException(status_code=403, detail="Compte business inactif")
    membership = await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.user_id == current_user.user_id,
            BusinessMembers.status == "active",
        )
    )
    allowed_roles = BUSINESS_PAYMENT_WRITE_ROLES if write else BUSINESS_PAYMENT_READ_ROLES
    if not membership or membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Acces business insuffisant")
    return business, membership


async def create_payment_request(
    db: AsyncSession,
    *,
    current_user: Users,
    payload: PaymentRequestCreate,
) -> PaymentRequests:
    amount = Decimal(payload.amount)
    currency_code = str(payload.currency_code or "").upper().strip()

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")
    if len(currency_code) != 3:
        raise HTTPException(status_code=400, detail="Devise invalide.")

    requester_wallet = await _get_user_wallet(db, current_user.user_id, currency_code)
    if not requester_wallet:
        raise HTTPException(status_code=404, detail="Wallet demandeur introuvable.")

    payer = None
    payer_wallet = None
    if payload.payer_identifier:
        payer = await _find_user_by_identifier(db, payload.payer_identifier)
        if not payer:
            raise HTTPException(status_code=404, detail="Payeur introuvable.")
        if payer.user_id == current_user.user_id:
            raise HTTPException(status_code=400, detail="Impossible de s'auto-adresser une demande.")
        payer_wallet = await _get_user_wallet(db, payer.user_id, currency_code)
        if not payer_wallet:
            raise HTTPException(status_code=404, detail="Wallet payeur introuvable.")

    now = _utcnow()
    if payload.due_at and payload.due_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="due_at doit contenir un fuseau horaire.")
    if payload.expires_at and payload.expires_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="expires_at doit contenir un fuseau horaire.")
    if payload.expires_at and payload.expires_at <= now:
        raise HTTPException(status_code=400, detail="expires_at doit etre dans le futur.")
    if payload.due_at and payload.expires_at and payload.due_at > payload.expires_at:
        raise HTTPException(status_code=400, detail="due_at doit preceder expires_at.")

    recurrence_config = _build_recurrence_config(payload, amount=amount)
    request_obj = PaymentRequests(
        requester_user_id=current_user.user_id,
        payer_user_id=payer.user_id if payer else None,
        requester_wallet_id=requester_wallet.wallet_id,
        payer_wallet_id=payer_wallet.wallet_id if payer_wallet else None,
        amount=amount,
        currency_code=currency_code,
        status="pending",
        channel=str(payload.channel or "direct").strip() or "direct",
        title=(payload.title or "").strip() or None,
        note=(payload.note or "").strip() or None,
        due_at=payload.due_at,
        expires_at=payload.expires_at,
        metadata_=recurrence_config,
        created_at=now,
        updated_at=now,
    )
    request_obj.share_token = _share_token(current_user.user_id, amount, now)
    db.add(request_obj)
    await db.flush()

    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="created",
        before_status=None,
        after_status=request_obj.status,
        metadata={"payer_identifier": payload.payer_identifier},
    )
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="sent",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={"channel": request_obj.channel},
    )

    if payer:
        await send_notification(
            str(payer.user_id),
            f"Nouvelle demande de paiement de {current_user.email or current_user.paytag or current_user.username} ({amount} {currency_code})",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def create_business_payment_request(
    db: AsyncSession,
    *,
    current_user: Users,
    business_id: UUID,
    payload: PaymentRequestCreate,
) -> PaymentRequests:
    amount = Decimal(payload.amount)
    currency_code = str(payload.currency_code or "").upper().strip()

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")
    if len(currency_code) != 3:
        raise HTTPException(status_code=400, detail="Devise invalide.")

    business, _membership = await _require_business_membership(
        db,
        business_id=business_id,
        current_user=current_user,
        write=True,
    )
    requester_wallet = await _get_user_wallet(db, business.owner_user_id, currency_code)
    if not requester_wallet:
        raise HTTPException(status_code=404, detail="Wallet business introuvable.")

    payer = None
    payer_wallet = None
    if payload.payer_identifier:
        payer = await _find_user_by_identifier(db, payload.payer_identifier)
        if not payer:
            raise HTTPException(status_code=404, detail="Payeur introuvable.")
        if payer.user_id == business.owner_user_id:
            raise HTTPException(status_code=400, detail="Impossible de cibler le proprietaire business comme payeur.")
        payer_wallet = await _get_user_wallet(db, payer.user_id, currency_code)
        if not payer_wallet:
            raise HTTPException(status_code=404, detail="Wallet payeur introuvable.")

    now = _utcnow()
    if payload.due_at and payload.due_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="due_at doit contenir un fuseau horaire.")
    if payload.expires_at and payload.expires_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="expires_at doit contenir un fuseau horaire.")
    if payload.expires_at and payload.expires_at <= now:
        raise HTTPException(status_code=400, detail="expires_at doit etre dans le futur.")
    if payload.due_at and payload.expires_at and payload.due_at > payload.expires_at:
        raise HTTPException(status_code=400, detail="due_at doit preceder expires_at.")

    business_label = business.display_name or business.legal_name
    recurrence_config = _build_recurrence_config(payload, amount=amount)
    metadata = {
        "scope": "business",
        "business_id": str(business.business_id),
        "business_label": business_label,
        "created_by_user_id": str(current_user.user_id),
        **recurrence_config,
    }
    merchant_reference = str(payload.merchant_reference or "").strip()
    if merchant_reference:
        metadata["merchant_reference"] = merchant_reference

    requested_channel = str(payload.channel or "").strip().lower()
    channel = BUSINESS_PAYMENT_CHANNEL_ALIASES.get(requested_channel)
    if not channel:
        raise HTTPException(
            status_code=400,
            detail="Canal invalide. Utilise business_link, static_qr ou dynamic_qr.",
        )

    request_obj = PaymentRequests(
        requester_user_id=business.owner_user_id,
        payer_user_id=payer.user_id if payer else None,
        requester_wallet_id=requester_wallet.wallet_id,
        payer_wallet_id=payer_wallet.wallet_id if payer_wallet else None,
        amount=amount,
        currency_code=currency_code,
        status="pending",
        channel=channel,
        title=(payload.title or "").strip() or business_label,
        note=(payload.note or "").strip() or None,
        due_at=payload.due_at,
        expires_at=payload.expires_at,
        metadata_=metadata,
        created_at=now,
        updated_at=now,
    )
    request_obj.share_token = _share_token(business.owner_user_id, amount, now)
    db.add(request_obj)
    await db.flush()

    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="created",
        before_status=None,
        after_status=request_obj.status,
        metadata={"business_id": str(business.business_id), "payer_identifier": payload.payer_identifier},
    )
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="sent",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={"channel": request_obj.channel, "business_id": str(business.business_id)},
    )

    if payer:
        await send_notification(
            str(payer.user_id),
            f"Nouvelle demande de paiement de {business_label} ({amount} {currency_code})",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def list_payment_requests(
    db: AsyncSession,
    *,
    current_user: Users,
    status: str | None = None,
) -> list[dict]:
    stmt = (
        select(PaymentRequests)
        .where(
            or_(
                PaymentRequests.requester_user_id == current_user.user_id,
                PaymentRequests.payer_user_id == current_user.user_id,
            )
        )
        .order_by(PaymentRequests.created_at.desc())
    )
    if status:
        stmt = stmt.where(PaymentRequests.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    changed = False
    for row in rows:
        changed = await _mark_expired_if_needed(db, row) or changed
    if changed:
        await db.commit()
    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )
    return [_serialize_request(item, current_user_id=current_user.user_id, users=users) for item in rows]


async def get_payment_request_detail(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
) -> dict:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    if current_user.user_id not in {request_obj.requester_user_id, request_obj.payer_user_id}:
        raise HTTPException(status_code=403, detail="Acces refuse.")

    changed = await _mark_expired_if_needed(db, request_obj)
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="viewed",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={},
    )
    await db.commit()
    if changed:
        await db.refresh(request_obj)

    events = (
        await db.execute(
            select(PaymentRequestEvents)
            .where(PaymentRequestEvents.request_id == request_id)
            .order_by(PaymentRequestEvents.created_at.desc())
        )
    ).scalars().all()
    users = await _users_map(db, [request_obj.requester_user_id, request_obj.payer_user_id])
    return {
        "request": _serialize_request(request_obj, current_user_id=current_user.user_id, users=users),
        "events": events,
    }


async def pay_payment_request(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
    reason: str | None = None,
) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")

    await _mark_expired_if_needed(db, request_obj)
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande ne peut plus etre payee.")
    if request_obj.payer_user_id and request_obj.payer_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le payeur cible peut payer cette demande.")
    if request_obj.requester_user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Le demandeur ne peut pas payer sa propre demande.")

    payer_wallet = await _get_user_wallet(db, current_user.user_id, request_obj.currency_code)
    requester_wallet = await db.scalar(select(Wallets).where(Wallets.wallet_id == request_obj.requester_wallet_id))
    if not payer_wallet or not requester_wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable.")
    if Decimal(payer_wallet.available or 0) < Decimal(request_obj.amount or 0):
        raise HTTPException(status_code=400, detail="Solde insuffisant.")

    payer_wallet.available = Decimal(payer_wallet.available or 0) - Decimal(request_obj.amount)
    requester_wallet.available = Decimal(requester_wallet.available or 0) + Decimal(request_obj.amount)

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=payer_wallet.wallet_id,
        receiver_wallet=requester_wallet.wallet_id,
        amount=request_obj.amount,
        currency_code=request_obj.currency_code,
        channel="internal",
        status="succeeded",
        description=request_obj.title or "Paiement demande de paiement",
    )
    db.add(tx)
    await db.flush()

    await log_wallet_movement(
        db,
        wallet=payer_wallet,
        user_id=current_user.user_id,
        amount=request_obj.amount,
        direction="debit",
        operation_type="payment_request_send",
        reference=str(request_obj.request_id),
        description=request_obj.title or "Paiement d'une demande",
    )
    await log_wallet_movement(
        db,
        wallet=requester_wallet,
        user_id=request_obj.requester_user_id,
        amount=request_obj.amount,
        direction="credit",
        operation_type="payment_request_receive",
        reference=str(request_obj.request_id),
        description=request_obj.title or "Reception d'une demande payee",
    )

    previous_status = request_obj.status
    now = _utcnow()
    request_obj.status = "paid"
    request_obj.payer_user_id = current_user.user_id
    request_obj.payer_wallet_id = payer_wallet.wallet_id
    request_obj.related_tx_id = tx.tx_id
    request_obj.paid_at = now
    request_obj.updated_at = now
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="paid",
        before_status=previous_status,
        after_status=request_obj.status,
        metadata={"reason": reason},
    )
    await _create_next_recurring_payment_request_if_needed(
        db,
        source_request=request_obj,
    )

    requester = await db.scalar(select(Users).where(Users.user_id == request_obj.requester_user_id))
    if requester:
        await send_notification(
            str(requester.user_id),
            f"Votre demande de paiement a ete payee par {current_user.email or current_user.paytag or current_user.username}.",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def _try_execute_due_autopay(
    db: AsyncSession,
    *,
    request_obj: PaymentRequests,
    users: dict[UUID, Users],
) -> bool:
    if request_obj.status != "pending" or not _is_due(request_obj):
        return False
    auto_pay_enabled, auto_pay_max_amount = _extract_auto_pay_config(request_obj.metadata_ or {})
    if not auto_pay_enabled:
        return False
    if not request_obj.payer_user_id:
        return False
    if auto_pay_max_amount is not None and Decimal(request_obj.amount or 0) > auto_pay_max_amount:
        return False

    payer = users.get(request_obj.payer_user_id)
    if not payer:
        payer = await db.get(Users, request_obj.payer_user_id)
        if payer:
            users[payer.user_id] = payer
    if not payer:
        return False

    try:
        await pay_payment_request(
            db,
            request_id=request_obj.request_id,
            current_user=payer,
            reason="auto_pay_due",
        )
        return True
    except HTTPException:
        return False


async def _create_next_recurring_payment_request_if_needed(
    db: AsyncSession,
    *,
    source_request: PaymentRequests,
) -> PaymentRequests | None:
    metadata = dict(source_request.metadata_ or {})
    recurrence = metadata.get("recurrence") if isinstance(metadata.get("recurrence"), dict) else {}
    frequency = str(recurrence.get("frequency") or "none").lower().strip()
    if frequency not in {"daily", "weekly", "monthly"}:
        return None
    if not source_request.due_at:
        return None

    recurrence_count = recurrence.get("count")
    if recurrence_count is not None:
        try:
            recurrence_count = int(recurrence_count)
        except Exception:
            recurrence_count = None
    if recurrence_count is not None and recurrence_count <= 1:
        return None

    next_due_at = _compute_next_due_at(source_request.due_at, frequency=frequency)
    recurrence_end_at = _parse_iso_datetime(recurrence.get("end_at"))
    if recurrence_end_at and next_due_at > recurrence_end_at:
        return None

    next_expires_at = _compute_next_expires_at(
        current_due_at=source_request.due_at,
        current_expires_at=source_request.expires_at,
        next_due_at=next_due_at,
    )

    next_recurrence = dict(recurrence)
    if recurrence_count is not None:
        next_recurrence["count"] = recurrence_count - 1
    metadata["recurrence"] = next_recurrence
    metadata["recurrence_root_request_id"] = str(metadata.get("recurrence_root_request_id") or source_request.request_id)
    metadata["recurrence_previous_request_id"] = str(source_request.request_id)
    metadata["reminder"] = _default_reminder_config()

    now = _utcnow()
    requester_wallet_id = source_request.requester_wallet_id
    payer_wallet_id = source_request.payer_wallet_id

    requester_wallet = await _get_user_wallet(db, source_request.requester_user_id, source_request.currency_code)
    if requester_wallet:
        requester_wallet_id = requester_wallet.wallet_id

    if source_request.payer_user_id:
        payer_wallet = await _get_user_wallet(db, source_request.payer_user_id, source_request.currency_code)
        if payer_wallet:
            payer_wallet_id = payer_wallet.wallet_id

    next_request = PaymentRequests(
        requester_user_id=source_request.requester_user_id,
        payer_user_id=source_request.payer_user_id,
        requester_wallet_id=requester_wallet_id,
        payer_wallet_id=payer_wallet_id,
        amount=source_request.amount,
        currency_code=source_request.currency_code,
        status="pending",
        channel=source_request.channel,
        title=source_request.title,
        note=source_request.note,
        due_at=next_due_at,
        expires_at=next_expires_at,
        metadata_=metadata,
        created_at=now,
        updated_at=now,
    )
    next_request.share_token = _share_token(source_request.requester_user_id, Decimal(source_request.amount or 0), now)
    db.add(next_request)
    await db.flush()

    await _append_event(
        db,
        request_id=next_request.request_id,
        actor_user_id=None,
        actor_role="system",
        event_type="created",
        before_status=None,
        after_status=next_request.status,
        metadata={"recurrence": {"generated_from": str(source_request.request_id)}},
    )
    await _append_event(
        db,
        request_id=next_request.request_id,
        actor_user_id=None,
        actor_role="system",
        event_type="sent",
        before_status=next_request.status,
        after_status=next_request.status,
        metadata={"channel": next_request.channel, "recurrence": {"auto_generated": True}},
    )

    if next_request.payer_user_id:
        await send_notification(
            str(next_request.payer_user_id),
            f"Nouvelle demande recurrente ({next_request.amount} {next_request.currency_code}).",
        )
    return next_request


async def decline_payment_request(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
    reason: str | None = None,
) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")

    await _mark_expired_if_needed(db, request_obj)
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande ne peut plus etre refusee.")
    if request_obj.payer_user_id and request_obj.payer_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le payeur cible peut refuser cette demande.")
    if request_obj.requester_user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Le demandeur ne peut pas refuser sa propre demande.")

    previous_status = request_obj.status
    now = _utcnow()
    request_obj.status = "declined"
    request_obj.payer_user_id = current_user.user_id
    request_obj.declined_at = now
    request_obj.updated_at = now
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="declined",
        before_status=previous_status,
        after_status=request_obj.status,
        metadata={"reason": reason},
    )

    requester = await db.scalar(select(Users).where(Users.user_id == request_obj.requester_user_id))
    if requester:
        await send_notification(
            str(requester.user_id),
            f"Votre demande de paiement a ete refusee par {current_user.email or current_user.paytag or current_user.username}.",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def cancel_payment_request(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
    reason: str | None = None,
) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    if request_obj.requester_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le demandeur peut annuler cette demande.")

    await _mark_expired_if_needed(db, request_obj)
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande ne peut plus etre annulee.")

    previous_status = request_obj.status
    now = _utcnow()
    request_obj.status = "cancelled"
    request_obj.cancelled_at = now
    request_obj.updated_at = now
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="cancelled",
        before_status=previous_status,
        after_status=request_obj.status,
        metadata={"reason": reason},
    )

    if request_obj.payer_user_id:
        await send_notification(
            str(request_obj.payer_user_id),
            f"Une demande de paiement a ete annulee par {current_user.email or current_user.paytag or current_user.username}.",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def remind_payment_request(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
    reason: str | None = None,
) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    if request_obj.requester_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le demandeur peut relancer cette demande.")

    await _mark_expired_if_needed(db, request_obj)
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande ne peut plus etre relancee.")
    if not request_obj.payer_user_id:
        raise HTTPException(status_code=400, detail="Aucun payeur cible pour cette relance.")

    now = _utcnow()
    reminder_fields = _extract_reminder_fields(request_obj.metadata_ or {}, now=now)
    next_manual_at = reminder_fields.get("next_manual_reminder_at")
    if not reminder_fields.get("can_send_manual_reminder", True):
        next_allowed_label = next_manual_at.isoformat() if isinstance(next_manual_at, datetime) else "plus tard"
        raise HTTPException(
            status_code=409,
            detail=f"Relance deja envoyee recemment. Prochaine relance manuelle autorisee apres {next_allowed_label}.",
        )

    request_obj.last_reminder_at = now
    request_obj.updated_at = now
    request_obj.metadata_ = _set_manual_reminder_metadata(request_obj.metadata_ or {}, now=now)
    db.add(
        PaymentRequestReminders(
            request_id=request_obj.request_id,
            reminder_type="manual",
            status="sent",
            scheduled_for=now,
            sent_at=now,
            metadata_={"reason": reason} if reason else {},
        )
    )
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="reminder_sent",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={"reason": reason},
    )

    await send_notification(
        str(request_obj.payer_user_id),
        f"Rappel de demande de paiement de {current_user.email or current_user.paytag or current_user.username} ({request_obj.amount} {request_obj.currency_code}).",
    )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def update_payment_request_auto_pay(
    db: AsyncSession,
    *,
    request_id: UUID,
    current_user: Users,
    enabled: bool,
    max_amount: Decimal | None = None,
    reason: str | None = None,
) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")

    await _mark_expired_if_needed(db, request_obj)
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Auto-pay ne peut etre modifiee que sur une demande en attente.")
    if not request_obj.payer_user_id or request_obj.payer_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le payeur cible peut configurer auto-pay.")

    request_amount = Decimal(str(request_obj.amount or 0))
    safe_max_amount: Decimal | None = None
    if enabled:
        safe_max_amount = Decimal(str(max_amount)) if max_amount is not None else request_amount
        if safe_max_amount < request_amount:
            raise HTTPException(
                status_code=400,
                detail="Le plafond auto-pay doit etre superieur ou egal au montant de la demande.",
            )

    metadata = dict(request_obj.metadata_ or {})
    auto_pay = metadata.get("auto_pay") if isinstance(metadata.get("auto_pay"), dict) else {}
    previous_enabled = bool(auto_pay.get("enabled") is True)
    previous_max_amount = auto_pay.get("max_amount")
    auto_pay["enabled"] = bool(enabled)
    auto_pay["max_amount"] = str(safe_max_amount) if safe_max_amount is not None else None
    metadata["auto_pay"] = auto_pay

    request_obj.metadata_ = metadata
    request_obj.updated_at = _utcnow()
    await _append_event(
        db,
        request_id=request_obj.request_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="autopay_updated",
        before_status=request_obj.status,
        after_status=request_obj.status,
        metadata={
            "reason": reason,
            "previous": {
                "enabled": previous_enabled,
                "max_amount": previous_max_amount,
            },
            "next": {
                "enabled": bool(enabled),
                "max_amount": auto_pay.get("max_amount"),
            },
        },
    )

    requester = await db.scalar(select(Users).where(Users.user_id == request_obj.requester_user_id))
    if requester:
        verb = "active" if enabled else "desactive"
        await send_notification(
            str(requester.user_id),
            f"Auto-pay a ete {verb} par le payeur pour la demande {request_obj.share_token or request_obj.request_id}.",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


async def get_payment_request_by_share_token(db: AsyncSession, token: str) -> PaymentRequests:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.share_token == token))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    changed = await _mark_expired_if_needed(db, request_obj)
    if changed:
        await db.commit()
    return request_obj


async def get_payment_request_public_view(db: AsyncSession, token: str) -> dict:
    request_obj = await get_payment_request_by_share_token(db, token)
    users = await _users_map(db, [request_obj.requester_user_id, request_obj.payer_user_id])
    requester = users.get(request_obj.requester_user_id)
    requester_label = _requester_label(request_obj, requester)
    now = _utcnow()
    recurrence_fields = _extract_recurrence_fields(request_obj.metadata_ or {})
    reminder_fields = _extract_reminder_fields(request_obj.metadata_ or {}, now=now)
    pay_url = _build_public_pay_url(request_obj.share_token)
    scan_to_pay_payload = _build_scan_to_pay_payload(request_obj)
    return {
        "request_id": request_obj.request_id,
        "requester_user_id": request_obj.requester_user_id,
        "payer_user_id": request_obj.payer_user_id,
        "amount": request_obj.amount,
        "currency_code": request_obj.currency_code,
        "status": request_obj.status,
        "channel": request_obj.channel,
        "title": request_obj.title,
        "note": request_obj.note,
        "share_token": request_obj.share_token,
        "public_pay_url": pay_url,
        "scan_to_pay_payload": scan_to_pay_payload,
        "due_at": request_obj.due_at,
        "expires_at": request_obj.expires_at,
        "paid_at": request_obj.paid_at,
        "declined_at": request_obj.declined_at,
        "cancelled_at": request_obj.cancelled_at,
        "last_reminder_at": request_obj.last_reminder_at,
        "metadata": request_obj.metadata_ or {},
        "created_at": request_obj.created_at,
        "updated_at": request_obj.updated_at,
        "counterpart_label": requester_label,
        "role": "public",
        "is_due": _is_due(request_obj, now),
        **recurrence_fields,
        **reminder_fields,
    }


def _serialize_admin_request(request_obj: PaymentRequests, users: dict[UUID, Users]) -> dict:
    now = _utcnow()
    requester = users.get(request_obj.requester_user_id)
    payer = users.get(request_obj.payer_user_id) if request_obj.payer_user_id else None
    requester_label = _requester_label(request_obj, requester)
    recurrence_fields = _extract_recurrence_fields(request_obj.metadata_ or {})
    reminder_fields = _extract_reminder_fields(request_obj.metadata_ or {}, now=now)
    pay_url = _build_public_pay_url(request_obj.share_token)
    scan_to_pay_payload = _build_scan_to_pay_payload(request_obj)
    return {
        "request_id": request_obj.request_id,
        "requester_user_id": request_obj.requester_user_id,
        "payer_user_id": request_obj.payer_user_id,
        "amount": request_obj.amount,
        "currency_code": request_obj.currency_code,
        "status": request_obj.status,
        "channel": request_obj.channel,
        "title": request_obj.title,
        "note": request_obj.note,
        "share_token": request_obj.share_token,
        "public_pay_url": pay_url,
        "scan_to_pay_payload": scan_to_pay_payload,
        "due_at": request_obj.due_at,
        "expires_at": request_obj.expires_at,
        "paid_at": request_obj.paid_at,
        "declined_at": request_obj.declined_at,
        "cancelled_at": request_obj.cancelled_at,
        "last_reminder_at": request_obj.last_reminder_at,
        "metadata": request_obj.metadata_ or {},
        "created_at": request_obj.created_at,
        "updated_at": request_obj.updated_at,
        "counterpart_label": None,
        "role": "admin",
        "requester_label": requester_label,
        "payer_label": _display_user(payer),
        "is_due": _is_due(request_obj, now),
        **recurrence_fields,
        **reminder_fields,
    }


async def run_due_payment_request_maintenance(
    db: AsyncSession,
    *,
    current_user: Users,
) -> dict:
    now = _utcnow()
    rows = (
        await db.execute(
            select(PaymentRequests)
            .where(
                PaymentRequests.requester_user_id == current_user.user_id,
                PaymentRequests.status == "pending",
                or_(
                    and_(PaymentRequests.expires_at.is_not(None), PaymentRequests.expires_at <= now),
                    and_(PaymentRequests.due_at.is_not(None), PaymentRequests.due_at <= now),
                ),
            )
            .order_by(PaymentRequests.created_at.desc())
        )
    ).scalars().all()

    reminded_count = 0
    expired_count = 0
    auto_paid_count = 0
    processed_ids: list[UUID] = []
    needs_commit = False
    requester_label = _display_user(current_user) or "utilisateur"
    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )

    for row in rows:
        if await _mark_expired_if_needed(db, row):
            expired_count += 1
            processed_ids.append(row.request_id)
            needs_commit = True
            continue
        if await _try_execute_due_autopay(db, request_obj=row, users=users):
            auto_paid_count += 1
            processed_ids.append(row.request_id)
            continue
        if await _send_due_reminder_if_needed(db, request_obj=row, requester_label=requester_label):
            reminded_count += 1
            processed_ids.append(row.request_id)
            needs_commit = True

    if needs_commit:
        await db.commit()

    processed_rows = []
    if processed_ids:
        processed_rows = (
            await db.execute(
                select(PaymentRequests)
                .where(PaymentRequests.request_id.in_(processed_ids))
                .order_by(PaymentRequests.created_at.desc())
            )
        ).scalars().all()
        users = await _users_map(
            db,
            [item.requester_user_id for item in processed_rows] + [item.payer_user_id for item in processed_rows],
        )

    return {
        "reminded_count": reminded_count,
        "expired_count": expired_count,
        "auto_paid_count": auto_paid_count,
        "processed_requests": [
            _serialize_request(item, current_user_id=current_user.user_id, users=users) for item in processed_rows
        ],
    }


async def run_global_due_payment_request_maintenance(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> dict:
    now = _utcnow()
    rows = (
        await db.execute(
            select(PaymentRequests)
            .where(
                PaymentRequests.status == "pending",
                or_(
                    and_(PaymentRequests.expires_at.is_not(None), PaymentRequests.expires_at <= now),
                    and_(PaymentRequests.due_at.is_not(None), PaymentRequests.due_at <= now),
                ),
            )
            .order_by(PaymentRequests.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    if not rows:
        return {"processed": 0, "reminded_count": 0, "expired_count": 0, "auto_paid_count": 0}

    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )

    processed_count = 0
    reminded_count = 0
    expired_count = 0
    auto_paid_count = 0
    needs_commit = False
    for row in rows:
        requester = users.get(row.requester_user_id)
        requester_label = _requester_label(row, requester) or "utilisateur"
        if await _mark_expired_if_needed(db, row):
            expired_count += 1
            processed_count += 1
            needs_commit = True
            continue
        if await _try_execute_due_autopay(db, request_obj=row, users=users):
            auto_paid_count += 1
            processed_count += 1
            continue
        if await _send_due_reminder_if_needed(db, request_obj=row, requester_label=requester_label):
            reminded_count += 1
            processed_count += 1
            needs_commit = True

    if needs_commit:
        await db.commit()

    return {
        "processed": processed_count,
        "reminded_count": reminded_count,
        "expired_count": expired_count,
        "auto_paid_count": auto_paid_count,
    }


async def list_business_payment_requests(
    db: AsyncSession,
    *,
    business_id: UUID,
    current_user: Users,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    business, _membership = await _require_business_membership(
        db,
        business_id=business_id,
        current_user=current_user,
        write=False,
    )
    stmt = (
        select(PaymentRequests)
        .where(PaymentRequests.metadata_["business_id"].astext == str(business.business_id))
        .order_by(PaymentRequests.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(PaymentRequests.status == str(status).strip())
    rows = (await db.execute(stmt)).scalars().all()
    changed = False
    for row in rows:
        changed = await _mark_expired_if_needed(db, row) or changed
    if changed:
        await db.commit()
    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )
    items = []
    for row in rows:
        item = _serialize_admin_request(row, users)
        item["role"] = "business"
        items.append(item)
    return items


async def get_business_payment_request_detail(
    db: AsyncSession,
    *,
    business_id: UUID,
    request_id: UUID,
    current_user: Users,
) -> dict:
    business, _membership = await _require_business_membership(
        db,
        business_id=business_id,
        current_user=current_user,
        write=False,
    )
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj or str((request_obj.metadata_ or {}).get("business_id") or "") != str(business.business_id):
        raise HTTPException(status_code=404, detail="Demande business introuvable.")
    changed = await _mark_expired_if_needed(db, request_obj)
    if changed:
        await db.commit()
    events = (
        await db.execute(
            select(PaymentRequestEvents)
            .where(PaymentRequestEvents.request_id == request_id)
            .order_by(PaymentRequestEvents.created_at.desc())
        )
    ).scalars().all()
    users = await _users_map(db, [request_obj.requester_user_id, request_obj.payer_user_id])
    payload = _serialize_admin_request(request_obj, users)
    payload["role"] = "business"
    return {
        "request": PaymentRequestAdminRead.model_validate(payload),
        "events": events,
    }


async def list_admin_payment_requests_v2(
    db: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    stmt = select(PaymentRequests).order_by(PaymentRequests.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(PaymentRequests.status == str(status).strip())
    if q:
        pattern = f"%{str(q).strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(PaymentRequests.title).ilike(pattern),
                func.lower(PaymentRequests.note).ilike(pattern),
                func.lower(PaymentRequests.share_token).ilike(pattern),
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    changed = False
    for row in rows:
        changed = await _mark_expired_if_needed(db, row) or changed
    if changed:
        await db.commit()
    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )
    return [_serialize_admin_request(item, users) for item in rows]


async def get_admin_payment_request_detail_v2(
    db: AsyncSession,
    *,
    request_id: UUID,
) -> dict:
    request_obj = await db.scalar(select(PaymentRequests).where(PaymentRequests.request_id == request_id))
    if not request_obj:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    changed = await _mark_expired_if_needed(db, request_obj)
    if changed:
        await db.commit()
    events = (
        await db.execute(
            select(PaymentRequestEvents)
            .where(PaymentRequestEvents.request_id == request_id)
            .order_by(PaymentRequestEvents.created_at.desc())
        )
    ).scalars().all()
    users = await _users_map(db, [request_obj.requester_user_id, request_obj.payer_user_id])
    return {
        "request": PaymentRequestAdminRead.model_validate(_serialize_admin_request(request_obj, users)),
        "events": events,
    }
