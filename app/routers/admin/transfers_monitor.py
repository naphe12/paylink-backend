from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, or_, desc, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.client_balance_events import ClientBalanceEvents
from app.models.wallet_transactions import WalletTransactions
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.general_settings import GeneralSettings
from app.models.external_transfers import ExternalTransfers

EXTERNAL_CHANNELS = {
    "external_transfer",
}

router = APIRouter(prefix="/admin/transfers", tags=["Admin Transfers"])

DESTINATION_CURRENCY_MAP = {
    "burundi": "BIF",
    "rwanda": "RWF",
    "drc": "CDF",
    "rd congo": "CDF",
    "democratic republic of congo": "CDF",
    "rdc": "CDF",
}


def _resolve_local_currency(country: str | None, stored_currency: str | None) -> str | None:
    """
    Ensure local_currency reflects destination country when legacy rows stored EUR.
    """
    if stored_currency and stored_currency != "EUR":
        return stored_currency
    key = (country or "").strip().lower()
    return DESTINATION_CURRENCY_MAP.get(key, stored_currency or None)


def serialize_decimal(value: Optional[Decimal]) -> float:
    return float(value or 0)


def _extract_transfer_flags(metadata: dict | None) -> dict:
    payload = dict(metadata or {})
    return {
        "review_reasons": list(payload.get("review_reasons") or []),
        "aml_reason_codes": list(payload.get("aml_reason_codes") or []),
        "aml_risk_score": payload.get("aml_risk_score"),
        "aml_manual_review_required": bool(payload.get("aml_manual_review_required")),
        "funding_pending": bool(payload.get("funding_pending")),
        "required_credit_topup": payload.get("required_credit_topup"),
    }


@router.get("")
@router.get("/")
async def list_external_transfers(
    status: Optional[str] = Query(
        None,
        description="Filtre par statut (pending, failed, succeeded, etc.)",
    ),
    channel: Optional[str] = Query(
        None,
        description="Filtre par channel (bank_transfer, mobile_money, ...)",
    ),
    user_id: Optional[UUID] = Query(
        None,
        description="Filtre par utilisateur (initiated_by)",
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    channel_param = channel.lower() if channel else None
    external_channels_lower = {c.lower() for c in EXTERNAL_CHANNELS}
    channel_field = func.lower(cast(Transactions.channel, String))

    stmt = (
        select(
            Transactions.tx_id,
            Transactions.amount,
            Transactions.currency_code,
            Transactions.channel,
            Transactions.status,
            Transactions.description,
            Transactions.created_at,
            Transactions.updated_at,
            Users.user_id,
            Users.full_name,
            Users.email,
            ExternalTransfers.local_amount,
            ExternalTransfers.currency.label("local_currency"),
            ExternalTransfers.country_destination,
            ExternalTransfers.reference_code,
            ExternalTransfers.metadata_.label("transfer_metadata"),
        )
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .join(
            ExternalTransfers,
            ExternalTransfers.transfer_id == Transactions.related_entity_id,
            isouter=True,
        )
        .where(channel_field != "internal")
        .order_by(Transactions.created_at.desc())
        .limit(limit)
    )

    if channel_param:
        stmt = stmt.where(channel_field == channel_param)
    elif channel is None:
        stmt = stmt.where(channel_field.in_(external_channels_lower))

    if user_id:
        stmt = stmt.where(Transactions.initiated_by == user_id)

    if status:
        if status.lower() == "pending":
            stmt = stmt.where(Transactions.status.in_(("pending", "initiated")))
        else:
            stmt = stmt.where(Transactions.status == status)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "tx_id": str(r.tx_id),
            "amount": serialize_decimal(r.amount),
            "currency": r.currency_code,
            "channel": r.channel,
            "status": r.status,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "initiator_id": str(r.user_id) if r.user_id else None,
            "initiator_name": r.full_name,
            "initiator_email": r.email,
            "local_amount": serialize_decimal(r.local_amount) if r.local_amount is not None else None,
            "local_currency": _resolve_local_currency(r.country_destination, r.local_currency),
            "reference_code": r.reference_code,
            "transfer_metadata": dict(r.transfer_metadata or {}),
            **_extract_transfer_flags(dict(r.transfer_metadata or {})),
        }
        for r in rows
    ]


@router.get("/detail/{transfer_ref}")
async def get_external_transfer_detail(
    transfer_ref: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    transfer_stmt = (
        select(
            Transactions,
            Users,
            ExternalTransfers,
        )
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .join(
            ExternalTransfers,
            ExternalTransfers.transfer_id == Transactions.related_entity_id,
            isouter=True,
        )
        .where(
            or_(
                cast(Transactions.tx_id, String) == transfer_ref,
                ExternalTransfers.reference_code == transfer_ref,
                cast(ExternalTransfers.transfer_id, String) == transfer_ref,
            )
        )
        .order_by(Transactions.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(transfer_stmt)).first()
    if row is None:
        return {"detail": "Transfert introuvable."}

    tx, user, transfer = row
    if transfer is None:
        return {"detail": "Transfert introuvable."}
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    return {
        "tx_id": str(getattr(tx, "tx_id", "") or "") or None,
        "transfer_id": str(transfer.transfer_id),
        "reference_code": transfer.reference_code,
        "transaction_status": str(getattr(tx, "status", "") or "") or None,
        "transfer_status": str(getattr(transfer, "status", "") or ""),
        "initiator": {
            "user_id": str(getattr(user, "user_id", "") or "") or None,
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
            "risk_score": getattr(user, "risk_score", None),
            "kyc_tier": getattr(user, "kyc_tier", None),
        },
        "beneficiary": {
            "recipient_name": transfer.recipient_name,
            "recipient_phone": transfer.recipient_phone,
            "partner_name": transfer.partner_name,
            "country_destination": transfer.country_destination,
        },
        "amounts": {
            "amount": serialize_decimal(transfer.amount),
            "destination_currency": transfer.currency,
            "local_amount": serialize_decimal(transfer.local_amount) if transfer.local_amount is not None else None,
            "local_currency": _resolve_local_currency(transfer.country_destination, transfer.currency),
            "rate": serialize_decimal(transfer.rate) if transfer.rate is not None else None,
        },
        "flags": _extract_transfer_flags(metadata),
        "metadata": metadata,
        "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
        "processed_at": transfer.processed_at.isoformat() if transfer.processed_at else None,
        "processed_by": str(transfer.processed_by) if transfer.processed_by else None,
    }


@router.get("/summary")
async def transfers_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    external_channels_lower = {c.lower() for c in EXTERNAL_CHANNELS}
    channel_field = func.lower(cast(Transactions.channel, String))
    stmt = (
        select(Transactions.status, func.count(Transactions.tx_id))
        .where(channel_field.in_(external_channels_lower))
        .group_by(Transactions.status)
    )
    rows = (await db.execute(stmt)).all()
    summary = {status: count for status, count in rows}

    succeeded = summary.get("succeeded", 0) + summary.get("completed", 0)
    pending = summary.get("pending", 0) + summary.get("initiated", 0)
    failed = summary.get("failed", 0) + summary.get("cancelled", 0)

    return {
        "pending": pending,
        "failed": failed,
        "succeeded": succeeded,
        "total": sum(summary.values()),
    }


@router.get("/gains")
async def transfers_gains(
    period: str = Query(
        "month",
        description="Filtre de temps: day, week, month, year",
        regex="^(day|week|month|year)$",
    ),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    charge_row = await db.execute(
        select(GeneralSettings.charge).order_by(GeneralSettings.created_at.desc()).limit(1)
    )
    charge_value = charge_row.scalar_one_or_none() or 0
    rate = float(charge_value)

    now = datetime.utcnow()
    if period == "week":
        date_from = now - timedelta(days=7)
    elif period == "month":
        date_from = now - timedelta(days=30)
    elif period == "year":
        date_from = now - timedelta(days=365)
    else:
        date_from = now - timedelta(days=1)

    success_statuses = {"succeeded", "completed"}
    target_channels = {"external_transfer", "cash"}
    status_field = func.lower(cast(Transactions.status, String))
    channel_field = func.lower(cast(Transactions.channel, String))

    bucket = func.date_trunc(period, Transactions.created_at).label("bucket")
    stmt = (
        select(
            channel_field.label("channel"),
            Transactions.currency_code.label("currency"),
            bucket,
            func.sum(Transactions.amount).label("amount_total"),
            func.count(Transactions.tx_id).label("count_total"),
        )
        .where(
            status_field.in_(success_statuses),
            channel_field.in_(target_channels),
            Transactions.created_at >= date_from,
        )
        .group_by(bucket, channel_field, Transactions.currency_code)
        .order_by(bucket.desc(), Transactions.currency_code.asc(), channel_field.asc())
    )

    rows = (await db.execute(stmt)).all()

    serialized = []
    total_count = 0
    totals_by_currency: dict[str, dict[str, float | int | str]] = {}

    for r in rows:
        amount = float(r.amount_total or 0)
        gain = amount * rate / 100
        currency = str(getattr(r, "currency", "") or "").strip().upper() or "UNKNOWN"
        serialized.append(
            {
                "day": r.bucket.isoformat() if r.bucket else None,
                "channel": r.channel,
                "currency": currency,
                "amount": round(amount, 2),
                "gain": round(gain, 2),
                "count": int(r.count_total or 0),
            }
        )
        currency_totals = totals_by_currency.setdefault(
            currency,
            {
                "currency": currency,
                "amount": 0.0,
                "gain": 0.0,
                "count": 0,
            },
        )
        currency_totals["amount"] = round(float(currency_totals["amount"]) + amount, 2)
        currency_totals["gain"] = round(float(currency_totals["gain"]) + gain, 2)
        currency_totals["count"] = int(currency_totals["count"]) + int(r.count_total or 0)
        total_count += int(r.count_total or 0)

    return {
        "period": period,
        "charge_rate": rate,
        "totals": {
            "count": total_count,
        },
        "totals_by_currency": list(totals_by_currency.values()),
        "rows": serialized,
    }


@router.get("/balance-events")
async def list_balance_events(
    user_id: UUID | None = Query(None),
    q: str | None = Query(None, description="Recherche nom/email/téléphone"),
    source: str | None = Query(None, description="Filtre exact sur la source"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    fetch_size = limit + offset
    legacy_stmt = (
        select(
            ClientBalanceEvents,
            Users.full_name,
            Users.email,
            Users.phone_e164,
        )
        .join(Users, Users.user_id == ClientBalanceEvents.user_id)
        .order_by(desc(ClientBalanceEvents.occurred_at))
        .limit(fetch_size)
    )
    wallet_stmt = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.user_id,
            WalletTransactions.amount,
            WalletTransactions.balance_after,
            WalletTransactions.currency_code,
            WalletTransactions.operation_type,
            WalletTransactions.created_at,
            cast(WalletTransactions.direction, String).label("direction"),
            Users.full_name,
            Users.email,
            Users.phone_e164,
        )
        .join(Users, Users.user_id == WalletTransactions.user_id)
        .order_by(desc(WalletTransactions.created_at))
        .limit(fetch_size)
    )

    if user_id:
        legacy_stmt = legacy_stmt.where(ClientBalanceEvents.user_id == user_id)
        wallet_stmt = wallet_stmt.where(WalletTransactions.user_id == user_id)
    if q:
        pattern = f"%{q}%"
        filters = or_(
            Users.full_name.ilike(pattern),
            Users.email.ilike(pattern),
            Users.phone_e164.ilike(pattern),
        )
        legacy_stmt = legacy_stmt.where(filters)
        wallet_stmt = wallet_stmt.where(filters)

    legacy_rows = (await db.execute(legacy_stmt)).all()
    wallet_rows = (await db.execute(wallet_stmt)).all()
    merged = [
        {
            "event_id": str(ev.event_id),
            "user_id": str(ev.user_id),
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "balance_before": float(ev.balance_before) if ev.balance_before is not None else None,
            "amount_delta": float(ev.amount_delta) if ev.amount_delta is not None else None,
            "balance_after": float(ev.balance_after) if ev.balance_after is not None else None,
            "currency": getattr(ev, "currency", None) or getattr(ev, "currency_code", None),
            "source": ev.source,
            "legacy_id": str(ev.legacy_id) if ev.legacy_id is not None else None,
            "occurred_at": ev.occurred_at,
            "created_at": ev.created_at,
        }
        for ev, full_name, email, phone in legacy_rows
    ]
    for (
        transaction_id,
        wallet_user_id,
        amount,
        balance_after_raw,
        currency_code,
        operation_type,
        created_at,
        direction_raw,
        full_name,
        email,
        phone,
    ) in wallet_rows:
        raw_amount = float(amount or 0)
        direction = str(direction_raw or "").lower()
        if direction == "in":
            direction = "credit"
        elif direction == "out":
            direction = "debit"
        signed_delta = raw_amount if direction == "credit" else -raw_amount
        balance_after = float(balance_after_raw) if balance_after_raw is not None else None
        balance_before = balance_after - signed_delta if balance_after is not None else None
        merged.append(
            {
                "event_id": f"wallet-{transaction_id}",
                "user_id": str(wallet_user_id) if wallet_user_id else None,
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "balance_before": balance_before,
                "amount_delta": signed_delta,
                "balance_after": balance_after,
                "currency": currency_code,
                "source": operation_type or "wallet_transaction",
                "occurred_at": created_at,
                "created_at": created_at,
            }
        )
    merged.sort(
        key=lambda item: item.get("occurred_at") or item.get("created_at"),
        reverse=True,
    )
    if source:
        normalized_source = source.strip().lower()
        merged = [
            item
            for item in merged
            if str(item.get("source") or "").strip().lower() == normalized_source
        ]
    return merged[offset : offset + limit]


@router.get("/users/{user_id}/balance-events")
async def list_user_balance_events(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    fetch_size = limit + offset
    legacy_stmt = (
        select(
            ClientBalanceEvents,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == ClientBalanceEvents.user_id)
        .where(ClientBalanceEvents.user_id == user_id)
        .order_by(desc(ClientBalanceEvents.occurred_at))
        .limit(fetch_size)
    )
    wallet_stmt = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.user_id,
            WalletTransactions.amount,
            WalletTransactions.balance_after,
            WalletTransactions.currency_code,
            WalletTransactions.operation_type,
            WalletTransactions.created_at,
            cast(WalletTransactions.direction, String).label("direction"),
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == WalletTransactions.user_id)
        .where(WalletTransactions.user_id == user_id)
        .order_by(desc(WalletTransactions.created_at))
        .limit(fetch_size)
    )
    legacy_rows = (await db.execute(legacy_stmt)).all()
    wallet_rows = (await db.execute(wallet_stmt)).all()
    merged = [
        {
            "event_id": str(ev.event_id),
            "user_id": str(ev.user_id),
            "full_name": full_name,
            "email": email,
            "balance_before": float(ev.balance_before) if ev.balance_before is not None else None,
            "amount_delta": float(ev.amount_delta) if ev.amount_delta is not None else None,
            "balance_after": float(ev.balance_after) if ev.balance_after is not None else None,
            "currency": getattr(ev, "currency", None) or getattr(ev, "currency_code", None),
            "source": ev.source,
            "occurred_at": ev.occurred_at,
            "created_at": ev.created_at,
        }
        for ev, full_name, email in legacy_rows
    ]
    for (
        transaction_id,
        wallet_user_id,
        amount,
        balance_after_raw,
        currency_code,
        operation_type,
        created_at,
        direction_raw,
        full_name,
        email,
    ) in wallet_rows:
        raw_amount = float(amount or 0)
        direction = str(direction_raw or "").lower()
        if direction == "in":
            direction = "credit"
        elif direction == "out":
            direction = "debit"
        signed_delta = raw_amount if direction == "credit" else -raw_amount
        balance_after = float(balance_after_raw) if balance_after_raw is not None else None
        balance_before = balance_after - signed_delta if balance_after is not None else None
        merged.append(
            {
                "event_id": f"wallet-{transaction_id}",
                "user_id": str(wallet_user_id) if wallet_user_id else None,
                "full_name": full_name,
                "email": email,
                "balance_before": balance_before,
                "amount_delta": signed_delta,
                "balance_after": balance_after,
                "currency": currency_code,
                "source": operation_type or "wallet_transaction",
                "occurred_at": created_at,
                "created_at": created_at,
            }
        )
    merged.sort(
        key=lambda item: item.get("occurred_at") or item.get("created_at"),
        reverse=True,
    )
    return merged[offset : offset + limit]


@router.get("/{transfer_ref}")
async def get_external_transfer_detail_legacy(
    transfer_ref: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await get_external_transfer_detail(transfer_ref=transfer_ref, db=db, admin=admin)

