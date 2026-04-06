from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import secrets
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transactions import Transactions
from app.models.users import Users
from app.models.virtual_card_transactions import VirtualCardTransactions
from app.models.virtual_cards import VirtualCards
from app.models.wallets import Wallets
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement

CARD_TYPES = {"standard", "single_use"}
CARD_STATUSES = {"active", "frozen", "cancelled", "consumed"}
MANAGEABLE_CARD_STATUSES = {"active", "frozen", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _normalize_category_token(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalized_blocked_categories(values) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for raw in values or []:
        normalized = _normalize_category_token(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _card_controls_metadata_payload(*, daily_limit, monthly_limit, blocked_categories) -> dict:
    return {
        "daily_limit": str(_to_decimal(daily_limit)),
        "monthly_limit": str(_to_decimal(monthly_limit)),
        "blocked_categories": _normalized_blocked_categories(blocked_categories),
    }


def _extract_card_controls(card: VirtualCards) -> dict:
    metadata = dict(card.metadata_ or {})
    controls = metadata.get("controls") or {}
    return {
        "daily_limit": _to_decimal(controls.get("daily_limit")),
        "monthly_limit": _to_decimal(controls.get("monthly_limit")),
        "blocked_categories": _normalized_blocked_categories(controls.get("blocked_categories") or []),
    }


def _empty_card_usage() -> dict:
    return {
        "daily_spent": Decimal("0"),
        "monthly_spent": Decimal("0"),
    }


def _validate_card_controls(*, daily_limit: Decimal, monthly_limit: Decimal) -> None:
    if daily_limit < 0 or monthly_limit < 0:
        raise HTTPException(status_code=400, detail="Les plafonds carte doivent etre positifs")
    if daily_limit > 0 and monthly_limit > 0 and daily_limit > monthly_limit:
        raise HTTPException(status_code=400, detail="Le plafond journalier ne peut pas depasser le plafond mensuel")


def _apply_card_controls_update(
    card: VirtualCards,
    *,
    daily_limit,
    monthly_limit,
    blocked_categories,
    actor_metadata: dict | None = None,
) -> None:
    normalized_daily_limit = _to_decimal(daily_limit)
    normalized_monthly_limit = _to_decimal(monthly_limit)
    _validate_card_controls(
        daily_limit=normalized_daily_limit,
        monthly_limit=normalized_monthly_limit,
    )
    metadata = dict(card.metadata_ or {})
    metadata["controls"] = _card_controls_metadata_payload(
        daily_limit=normalized_daily_limit,
        monthly_limit=normalized_monthly_limit,
        blocked_categories=blocked_categories,
    )
    if actor_metadata:
        metadata["last_controls_update"] = actor_metadata
    card.metadata_ = metadata
    card.updated_at = _now()


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


def _luhn_checksum_digit(number_without_checksum: str) -> str:
    digits = [int(ch) for ch in number_without_checksum]
    parity = (len(digits) + 1) % 2
    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - (total % 10)) % 10)


def _generate_plain_pan() -> str:
    body = f"426390{secrets.randbelow(10**9):09d}"
    return f"{body}{_luhn_checksum_digit(body)}"


def _generate_cvv() -> str:
    return f"{secrets.randbelow(1000):03d}"


def _mask_pan(pan: str) -> str:
    return f"{pan[:4]} **** **** {pan[-4:]}"


def _serialize_card_transaction(item: VirtualCardTransactions) -> dict:
    return {
        "card_tx_id": item.card_tx_id,
        "card_id": item.card_id,
        "user_id": item.user_id,
        "merchant_name": item.merchant_name,
        "merchant_category": item.merchant_category,
        "amount": _to_decimal(item.amount),
        "currency_code": item.currency_code,
        "status": item.status,
        "decline_reason": item.decline_reason,
        "reference": item.reference,
        "metadata": dict(item.metadata_ or {}),
        "created_at": item.created_at,
    }


def _compute_utilization_percent(card: VirtualCards) -> float:
    spending_limit = _to_decimal(card.spending_limit)
    spent_amount = _to_decimal(card.spent_amount)
    if spending_limit <= 0:
        return 0.0
    return float(round((spent_amount / spending_limit) * Decimal("100"), 2))


def _serialize_card(
    card: VirtualCards,
    *,
    transactions: list[VirtualCardTransactions] | None = None,
    usage_metrics: dict | None = None,
    plain_pan: str | None = None,
    plain_cvv: str | None = None,
) -> dict:
    controls = _extract_card_controls(card)
    usage = usage_metrics or _empty_card_usage()
    daily_limit = _to_decimal(controls.get("daily_limit"))
    monthly_limit = _to_decimal(controls.get("monthly_limit"))
    daily_spent = _to_decimal(usage.get("daily_spent"))
    monthly_spent = _to_decimal(usage.get("monthly_spent"))
    last_decline_reason = next(
        (
            item.decline_reason
            for item in (transactions or [])
            if item.status == "declined" and item.decline_reason
        ),
        None,
    )
    return {
        "card_id": card.card_id,
        "user_id": card.user_id,
        "linked_wallet_id": card.linked_wallet_id,
        "cardholder_name": card.cardholder_name,
        "brand": card.brand,
        "card_type": card.card_type,
        "currency_code": card.currency_code,
        "masked_pan": card.masked_pan,
        "last4": card.last4,
        "exp_month": card.exp_month,
        "exp_year": card.exp_year,
        "spending_limit": _to_decimal(card.spending_limit),
        "spent_amount": _to_decimal(card.spent_amount),
        "daily_limit": daily_limit,
        "monthly_limit": monthly_limit,
        "blocked_categories": controls.get("blocked_categories") or [],
        "daily_spent": daily_spent,
        "monthly_spent": monthly_spent,
        "daily_remaining": max(daily_limit - daily_spent, Decimal("0")) if daily_limit > 0 else None,
        "monthly_remaining": max(monthly_limit - monthly_spent, Decimal("0")) if monthly_limit > 0 else None,
        "last_decline_reason": last_decline_reason,
        "status": card.status,
        "frozen_at": card.frozen_at,
        "cancelled_at": card.cancelled_at,
        "last_used_at": card.last_used_at,
        "metadata": dict(card.metadata_ or {}),
        "created_at": card.created_at,
        "updated_at": card.updated_at,
        "plain_pan": plain_pan,
        "plain_cvv": plain_cvv,
        "transactions": [_serialize_card_transaction(item) for item in (transactions or [])],
    }


def _serialize_admin_card(
    card: VirtualCards,
    *,
    user: Users | None,
    transactions: list[VirtualCardTransactions] | None = None,
    usage_metrics: dict | None = None,
    transaction_count: int = 0,
    declined_count: int = 0,
) -> dict:
    payload = _serialize_card(
        card,
        transactions=transactions or [],
        usage_metrics=usage_metrics,
    )
    payload.update(
        {
            "user_label": (
                user.full_name
                or user.email
                or user.paytag
                or user.username
                or str(card.user_id)
            )
            if user
            else str(card.user_id),
            "user_email": user.email if user else None,
            "user_paytag": user.paytag if user else None,
            "user_role": user.role if user else None,
            "transaction_count": int(transaction_count or 0),
            "declined_count": int(declined_count or 0),
            "utilization_percent": _compute_utilization_percent(card),
        }
    )
    return payload


def _apply_card_status_update(card: VirtualCards, next_status: str) -> None:
    if next_status not in MANAGEABLE_CARD_STATUSES:
        raise HTTPException(status_code=400, detail="Statut carte invalide")
    if card.status == "consumed" and next_status != "consumed":
        raise HTTPException(status_code=400, detail="Une carte a usage unique consommee ne peut plus etre reactivee")
    if card.status == "cancelled" and next_status != "cancelled":
        raise HTTPException(status_code=400, detail="Une carte annulee ne peut plus etre reactivee")

    now = _now()
    card.status = next_status
    card.updated_at = now
    if next_status == "frozen":
        card.frozen_at = now
    elif next_status == "active":
        card.frozen_at = None
    elif next_status == "cancelled":
        card.cancelled_at = now


async def _get_card_for_user(db: AsyncSession, *, current_user: Users, card_id: UUID, lock: bool = False) -> VirtualCards:
    stmt = select(VirtualCards).where(
        VirtualCards.card_id == card_id,
        VirtualCards.user_id == current_user.user_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    card = await db.scalar(stmt)
    if not card:
        raise HTTPException(status_code=404, detail="Carte virtuelle introuvable")
    return card


async def _get_linked_wallet_for_card(db: AsyncSession, *, card: VirtualCards, current_user: Users) -> Wallets:
    wallet = None
    if card.linked_wallet_id:
        wallet = await db.scalar(
            select(Wallets)
            .where(Wallets.wallet_id == card.linked_wallet_id, Wallets.user_id == current_user.user_id)
            .with_for_update()
        )
    if not wallet:
        wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet lie a la carte introuvable")
    return wallet


async def _load_card_transactions(db: AsyncSession, card_ids: list[UUID]) -> dict[UUID, list[VirtualCardTransactions]]:
    if not card_ids:
        return {}
    rows = (
        await db.execute(
            select(VirtualCardTransactions)
            .where(VirtualCardTransactions.card_id.in_(card_ids))
            .order_by(VirtualCardTransactions.created_at.desc())
        )
    ).scalars().all()
    grouped: dict[UUID, list[VirtualCardTransactions]] = {}
    for row in rows:
        grouped.setdefault(row.card_id, []).append(row)
    return grouped


async def _load_card_usage_metrics(db: AsyncSession, card_ids: list[UUID]) -> dict[UUID, dict]:
    if not card_ids:
        return {}
    now = _now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = (
        await db.execute(
            select(
                VirtualCardTransactions.card_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    VirtualCardTransactions.status == "authorized",
                                    VirtualCardTransactions.created_at >= day_start,
                                ),
                                VirtualCardTransactions.amount,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("daily_spent"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    VirtualCardTransactions.status == "authorized",
                                    VirtualCardTransactions.created_at >= month_start,
                                ),
                                VirtualCardTransactions.amount,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("monthly_spent"),
            )
            .where(VirtualCardTransactions.card_id.in_(card_ids))
            .group_by(VirtualCardTransactions.card_id)
        )
    ).all()
    metrics: dict[UUID, dict] = {}
    for card_id, daily_spent, monthly_spent in rows:
        metrics[card_id] = {
            "daily_spent": _to_decimal(daily_spent),
            "monthly_spent": _to_decimal(monthly_spent),
        }
    return metrics


async def _record_card_transaction(
    db: AsyncSession,
    *,
    card: VirtualCards,
    current_user: Users,
    merchant_name: str,
    merchant_category: str | None,
    amount: Decimal,
    status: str,
    reference: str,
    decline_reason: str | None = None,
    metadata: dict | None = None,
) -> VirtualCardTransactions:
    item = VirtualCardTransactions(
        card_id=card.card_id,
        user_id=current_user.user_id,
        merchant_name=merchant_name,
        merchant_category=merchant_category,
        amount=amount,
        currency_code=card.currency_code,
        status=status,
        decline_reason=decline_reason,
        reference=reference,
        metadata_=metadata or {},
    )
    db.add(item)
    await db.flush()
    return item


def _human_decline_message(reason: str) -> str:
    messages = {
        "card_frozen": "La carte est gelee",
        "card_cancelled": "La carte est annulee",
        "card_consumed": "La carte a deja ete consommee",
        "spending_limit_exceeded": "Le plafond de la carte serait depasse",
        "daily_limit_exceeded": "Le plafond journalier de la carte serait depasse",
        "monthly_limit_exceeded": "Le plafond mensuel de la carte serait depasse",
        "merchant_category_blocked": "Cette categorie marchande est bloquee sur la carte",
        "insufficient_funds": "Solde insuffisant sur le wallet lie",
    }
    return messages.get(reason, "Paiement carte refuse")


async def list_virtual_cards(db: AsyncSession, *, current_user: Users) -> list[dict]:
    cards = (
        await db.execute(
            select(VirtualCards)
            .where(VirtualCards.user_id == current_user.user_id)
            .order_by(VirtualCards.created_at.desc())
        )
    ).scalars().all()
    grouped_transactions = await _load_card_transactions(db, [card.card_id for card in cards])
    grouped_usage = await _load_card_usage_metrics(db, [card.card_id for card in cards])
    return [
        _serialize_card(
            card,
            transactions=grouped_transactions.get(card.card_id, []),
            usage_metrics=grouped_usage.get(card.card_id, _empty_card_usage()),
        )
        for card in cards
    ]


async def get_virtual_card_detail(db: AsyncSession, *, current_user: Users, card_id: UUID) -> dict:
    card = await _get_card_for_user(db, current_user=current_user, card_id=card_id)
    grouped_transactions = await _load_card_transactions(db, [card.card_id])
    grouped_usage = await _load_card_usage_metrics(db, [card.card_id])
    return _serialize_card(
        card,
        transactions=grouped_transactions.get(card.card_id, []),
        usage_metrics=grouped_usage.get(card.card_id, _empty_card_usage()),
    )


async def create_virtual_card(db: AsyncSession, *, current_user: Users, payload) -> dict:
    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Aucun wallet principal disponible")

    card_type = str(payload.card_type or "standard").strip().lower()
    if card_type not in CARD_TYPES:
        raise HTTPException(status_code=400, detail="Type de carte invalide")

    now = _now()
    plain_pan = _generate_plain_pan()
    plain_cvv = _generate_cvv()
    cardholder_name = str(payload.cardholder_name or current_user.full_name or "PESAPAID USER").strip() or "PESAPAID USER"
    item = VirtualCards(
        user_id=current_user.user_id,
        linked_wallet_id=wallet.wallet_id,
        cardholder_name=cardholder_name,
        brand="visa",
        card_type=card_type,
        currency_code=str(wallet.currency_code or "").upper(),
        masked_pan=_mask_pan(plain_pan),
        last4=plain_pan[-4:],
        exp_month=now.month,
        exp_year=now.year + 3,
        spending_limit=_to_decimal(payload.spending_limit),
        spent_amount=Decimal("0"),
        status="active",
        metadata_={
            "test_mode": True,
            "controls": _card_controls_metadata_payload(
                daily_limit=payload.daily_limit,
                monthly_limit=payload.monthly_limit,
                blocked_categories=payload.blocked_categories,
            ),
        },
    )
    _validate_card_controls(
        daily_limit=_to_decimal(payload.daily_limit),
        monthly_limit=_to_decimal(payload.monthly_limit),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_card(
        item,
        plain_pan=plain_pan,
        plain_cvv=plain_cvv,
        transactions=[],
        usage_metrics=_empty_card_usage(),
    )


async def update_virtual_card_status(db: AsyncSession, *, current_user: Users, card_id: UUID, payload) -> dict:
    card = await _get_card_for_user(db, current_user=current_user, card_id=card_id, lock=True)
    next_status = str(payload.status or "").strip().lower()
    _apply_card_status_update(card, next_status)
    await db.commit()
    return await get_virtual_card_detail(db, current_user=current_user, card_id=card_id)


async def update_virtual_card_controls(db: AsyncSession, *, current_user: Users, card_id: UUID, payload) -> dict:
    card = await _get_card_for_user(db, current_user=current_user, card_id=card_id, lock=True)
    _apply_card_controls_update(
        card,
        daily_limit=payload.daily_limit,
        monthly_limit=payload.monthly_limit,
        blocked_categories=payload.blocked_categories,
        actor_metadata={
            "actor_user_id": str(current_user.user_id),
            "actor_role": current_user.role,
            "updated_at": _now().isoformat(),
        },
    )
    await db.commit()
    return await get_virtual_card_detail(db, current_user=current_user, card_id=card_id)


async def charge_virtual_card(db: AsyncSession, *, current_user: Users, card_id: UUID, payload) -> dict:
    card = await _get_card_for_user(db, current_user=current_user, card_id=card_id, lock=True)
    wallet = await _get_linked_wallet_for_card(db, card=card, current_user=current_user)
    amount = _to_decimal(payload.amount)
    merchant_name = str(payload.merchant_name or "").strip()
    merchant_category = str(payload.merchant_category or "").strip() or None
    merchant_category_key = _normalize_category_token(merchant_category)
    if not merchant_name:
        raise HTTPException(status_code=400, detail="Nom marchand requis")

    spent_amount = _to_decimal(card.spent_amount)
    spending_limit = _to_decimal(card.spending_limit)
    wallet_available = _to_decimal(wallet.available)
    controls = _extract_card_controls(card)
    usage = (await _load_card_usage_metrics(db, [card.card_id])).get(card.card_id, _empty_card_usage())
    daily_limit = _to_decimal(controls.get("daily_limit"))
    monthly_limit = _to_decimal(controls.get("monthly_limit"))
    blocked_categories = controls.get("blocked_categories") or []

    decline_reason = None
    if card.status == "frozen":
        decline_reason = "card_frozen"
    elif card.status == "cancelled":
        decline_reason = "card_cancelled"
    elif card.status == "consumed" or (card.card_type == "single_use" and spent_amount > 0):
        decline_reason = "card_consumed"
    elif spending_limit > 0 and spent_amount + amount > spending_limit:
        decline_reason = "spending_limit_exceeded"
    elif merchant_category_key and merchant_category_key in blocked_categories:
        decline_reason = "merchant_category_blocked"
    elif daily_limit > 0 and _to_decimal(usage.get("daily_spent")) + amount > daily_limit:
        decline_reason = "daily_limit_exceeded"
    elif monthly_limit > 0 and _to_decimal(usage.get("monthly_spent")) + amount > monthly_limit:
        decline_reason = "monthly_limit_exceeded"
    elif wallet_available < amount:
        decline_reason = "insufficient_funds"

    if decline_reason:
        if card.card_type == "single_use" and spent_amount > 0 and card.status != "consumed":
            card.status = "consumed"
            card.updated_at = _now()
        await _record_card_transaction(
            db,
            card=card,
            current_user=current_user,
            merchant_name=merchant_name,
            merchant_category=merchant_category,
            amount=amount,
            status="declined",
            reference=f"vcard-decline-{secrets.token_hex(8)}",
            decline_reason=decline_reason,
            metadata={
                "attempted": True,
                "controls_snapshot": {
                    "daily_limit": str(daily_limit),
                    "monthly_limit": str(monthly_limit),
                    "blocked_categories": blocked_categories,
                    "daily_spent": str(_to_decimal(usage.get("daily_spent"))),
                    "monthly_spent": str(_to_decimal(usage.get("monthly_spent"))),
                },
            },
        )
        await db.commit()
        raise HTTPException(status_code=400, detail=_human_decline_message(decline_reason))

    now = _now()
    wallet.available = wallet_available - amount
    card.spent_amount = spent_amount + amount
    card.last_used_at = now
    card.updated_at = now
    if card.card_type == "single_use":
        card.status = "consumed"

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=wallet.wallet_id,
        receiver_wallet=wallet.wallet_id,
        amount=amount,
        currency_code=wallet.currency_code,
        channel="card",
        status="succeeded",
        related_entity_id=card.card_id,
        description=f"Paiement carte virtuelle {merchant_name}",
    )
    db.add(tx)
    await db.flush()

    wallet_movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="virtual_card_charge",
        reference=str(card.card_id),
        description=f"Paiement carte virtuelle {merchant_name}",
    )

    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    card_account = await ledger.ensure_system_account(
        code=f"VIRTUAL_CARD::{card.card_id}",
        name=f"Carte virtuelle {card.last4}",
        currency_code=card.currency_code,
        metadata={
            "kind": "virtual_card",
            "card_id": str(card.card_id),
            "user_id": str(current_user.user_id),
        },
    )
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=f"Paiement carte virtuelle {merchant_name}",
        metadata={
            "operation": "virtual_card_charge",
            "card_id": str(card.card_id),
            "wallet_id": str(wallet.wallet_id),
            "merchant_name": merchant_name,
            "merchant_category": merchant_category,
            "wallet_movement_id": str(wallet_movement.transaction_id) if wallet_movement else None,
        },
        entries=[
            LedgerLine(account=wallet_account, direction="debit", amount=amount, currency_code=wallet.currency_code),
            LedgerLine(account=card_account, direction="credit", amount=amount, currency_code=card.currency_code),
        ],
    )

    await _record_card_transaction(
        db,
        card=card,
        current_user=current_user,
        merchant_name=merchant_name,
        merchant_category=merchant_category,
        amount=amount,
        status="authorized",
        reference=str(tx.tx_id),
        metadata={"wallet_id": str(wallet.wallet_id)},
    )

    await db.commit()
    return await get_virtual_card_detail(db, current_user=current_user, card_id=card.card_id)


async def list_admin_virtual_cards(
    db: AsyncSession,
    *,
    status: str | None = None,
    card_type: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    metrics_subquery = (
        select(
            VirtualCardTransactions.card_id.label("card_id"),
            func.count(VirtualCardTransactions.card_tx_id).label("transaction_count"),
            func.count(case((VirtualCardTransactions.status == "declined", 1))).label("declined_count"),
        )
        .group_by(VirtualCardTransactions.card_id)
        .subquery()
    )

    stmt = (
        select(
            VirtualCards,
            Users,
            func.coalesce(metrics_subquery.c.transaction_count, 0),
            func.coalesce(metrics_subquery.c.declined_count, 0),
        )
        .join(Users, Users.user_id == VirtualCards.user_id)
        .outerjoin(metrics_subquery, metrics_subquery.c.card_id == VirtualCards.card_id)
        .order_by(VirtualCards.created_at.desc())
        .limit(limit)
    )

    if status:
        stmt = stmt.where(VirtualCards.status == status)
    if card_type:
        stmt = stmt.where(VirtualCards.card_type == card_type)
    if q and q.strip():
        search = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(VirtualCards.cardholder_name).like(search),
                func.lower(VirtualCards.masked_pan).like(search),
                func.lower(VirtualCards.last4).like(search),
                func.lower(func.coalesce(Users.full_name, "")).like(search),
                func.lower(func.coalesce(Users.email, "")).like(search),
                func.lower(func.coalesce(Users.paytag, "")).like(search),
                func.lower(func.coalesce(Users.username, "")).like(search),
            )
        )

    rows = (await db.execute(stmt)).all()
    grouped_usage = await _load_card_usage_metrics(db, [card.card_id for card, _, _, _ in rows])
    return [
        _serialize_admin_card(
            card,
            user=user,
            usage_metrics=grouped_usage.get(card.card_id, _empty_card_usage()),
            transaction_count=transaction_count,
            declined_count=declined_count,
        )
        for card, user, transaction_count, declined_count in rows
    ]


async def get_admin_virtual_card_detail(db: AsyncSession, *, card_id: UUID) -> dict:
    row = (
        await db.execute(
            select(VirtualCards, Users)
            .join(Users, Users.user_id == VirtualCards.user_id)
            .where(VirtualCards.card_id == card_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Carte virtuelle introuvable")

    card, user = row
    grouped_transactions = await _load_card_transactions(db, [card.card_id])
    grouped_usage = await _load_card_usage_metrics(db, [card.card_id])
    transactions = grouped_transactions.get(card.card_id, [])
    declined_count = sum(1 for item in transactions if item.status == "declined")
    return _serialize_admin_card(
        card,
        user=user,
        transactions=transactions,
        usage_metrics=grouped_usage.get(card.card_id, _empty_card_usage()),
        transaction_count=len(transactions),
        declined_count=declined_count,
    )


async def update_admin_virtual_card_status(
    db: AsyncSession,
    *,
    card_id: UUID,
    payload,
    current_admin: Users,
) -> dict:
    card = await db.scalar(select(VirtualCards).where(VirtualCards.card_id == card_id).with_for_update())
    if not card:
        raise HTTPException(status_code=404, detail="Carte virtuelle introuvable")
    next_status = str(payload.status or "").strip().lower()
    _apply_card_status_update(card, next_status)
    metadata = dict(card.metadata_ or {})
    metadata["last_admin_action"] = {
        "admin_user_id": str(current_admin.user_id),
        "status": next_status,
        "at": _now().isoformat(),
    }
    card.metadata_ = metadata
    await db.commit()
    return await get_admin_virtual_card_detail(db, card_id=card_id)


async def update_admin_virtual_card_controls(
    db: AsyncSession,
    *,
    card_id: UUID,
    payload,
    current_admin: Users,
) -> dict:
    card = await db.scalar(select(VirtualCards).where(VirtualCards.card_id == card_id).with_for_update())
    if not card:
        raise HTTPException(status_code=404, detail="Carte virtuelle introuvable")
    _apply_card_controls_update(
        card,
        daily_limit=payload.daily_limit,
        monthly_limit=payload.monthly_limit,
        blocked_categories=payload.blocked_categories,
        actor_metadata={
            "actor_user_id": str(current_admin.user_id),
            "actor_role": current_admin.role,
            "updated_at": _now().isoformat(),
            "scope": "admin",
        },
    )
    await db.commit()
    return await get_admin_virtual_card_detail(db, card_id=card_id)
