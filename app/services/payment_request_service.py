from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
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
        metadata_={},
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
    metadata = {
        "scope": "business",
        "business_id": str(business.business_id),
        "business_label": business_label,
        "created_by_user_id": str(current_user.user_id),
    }
    merchant_reference = str(payload.merchant_reference or "").strip()
    if merchant_reference:
        metadata["merchant_reference"] = merchant_reference

    request_obj = PaymentRequests(
        requester_user_id=business.owner_user_id,
        payer_user_id=payer.user_id if payer else None,
        requester_wallet_id=requester_wallet.wallet_id,
        payer_wallet_id=payer_wallet.wallet_id if payer_wallet else None,
        amount=amount,
        currency_code=currency_code,
        status="pending",
        channel="business_link",
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

    requester = await db.scalar(select(Users).where(Users.user_id == request_obj.requester_user_id))
    if requester:
        await send_notification(
            str(requester.user_id),
            f"Votre demande de paiement a ete payee par {current_user.email or current_user.paytag or current_user.username}.",
        )

    await db.commit()
    await db.refresh(request_obj)
    return request_obj


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
    request_obj.last_reminder_at = now
    request_obj.updated_at = now
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
    }


def _serialize_admin_request(request_obj: PaymentRequests, users: dict[UUID, Users]) -> dict:
    now = _utcnow()
    requester = users.get(request_obj.requester_user_id)
    payer = users.get(request_obj.payer_user_id) if request_obj.payer_user_id else None
    requester_label = _requester_label(request_obj, requester)
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
    processed: list[PaymentRequests] = []
    requester_label = _display_user(current_user) or "utilisateur"

    for row in rows:
        if await _mark_expired_if_needed(db, row):
            expired_count += 1
            processed.append(row)
            continue
        if await _send_due_reminder_if_needed(db, request_obj=row, requester_label=requester_label):
            reminded_count += 1
            processed.append(row)

    if processed:
        await db.commit()

    users = await _users_map(
        db,
        [item.requester_user_id for item in processed] + [item.payer_user_id for item in processed],
    )
    return {
        "reminded_count": reminded_count,
        "expired_count": expired_count,
        "processed_requests": [
            _serialize_request(item, current_user_id=current_user.user_id, users=users) for item in processed
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
        return {"processed": 0, "reminded_count": 0, "expired_count": 0}

    users = await _users_map(
        db,
        [item.requester_user_id for item in rows] + [item.payer_user_id for item in rows],
    )

    processed_count = 0
    reminded_count = 0
    expired_count = 0
    for row in rows:
        requester = users.get(row.requester_user_id)
        requester_label = _requester_label(row, requester) or "utilisateur"
        if await _mark_expired_if_needed(db, row):
            expired_count += 1
            processed_count += 1
            continue
        if await _send_due_reminder_if_needed(db, request_obj=row, requester_label=requester_label):
            reminded_count += 1
            processed_count += 1

    if processed_count:
        await db.commit()

    return {
        "processed": processed_count,
        "reminded_count": reminded_count,
        "expired_count": expired_count,
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
