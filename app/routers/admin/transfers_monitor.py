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
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.general_settings import GeneralSettings
from app.models.external_transfers import ExternalTransfers

EXTERNAL_CHANNELS = {
    "external_transfer",
}

router = APIRouter(prefix="/admin/transfers", tags=["Admin Transfers"])


def serialize_decimal(value: Optional[Decimal]) -> float:
    return float(value or 0)


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

    if status:
        if status.lower() == "pending":
            # si on demande pending, on renvoie tout sauf pending
            stmt = stmt.where(Transactions.status != "pending")
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
            "local_currency": r.local_currency,
        }
        for r in rows
    ]


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
        "day",
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

    bucket = func.date_trunc(period, Transactions.created_at).label("bucket")
    stmt = (
        select(
            Transactions.channel,
            bucket,
            func.sum(Transactions.amount).label("amount_total"),
            func.count(Transactions.tx_id).label("count_total"),
        )
        .where(
            Transactions.status.in_(success_statuses),
            Transactions.channel.in_(target_channels),
            Transactions.created_at >= date_from,
        )
        .group_by(bucket, Transactions.channel)
        .order_by(bucket.desc())
    )

    rows = (await db.execute(stmt)).all()

    serialized = []
    total_amount = 0.0
    total_gain = 0.0
    total_count = 0

    for r in rows:
        amount = float(r.amount_total or 0)
        gain = amount * rate / 100
        serialized.append(
            {
                "day": r.bucket.isoformat() if r.bucket else None,
                "channel": r.channel,
                "amount": round(amount, 2),
                "gain": round(gain, 2),
                "count": int(r.count_total or 0),
            }
        )
        total_amount += amount
        total_gain += gain
        total_count += int(r.count_total or 0)

    return {
        "period": period,
        "charge_rate": rate,
        "totals": {
            "amount": round(total_amount, 2),
            "gain": round(total_gain, 2),
            "count": total_count,
        },
        "rows": serialized,
    }


@router.get("/balance-events")
async def list_balance_events(
    user_id: UUID | None = Query(None),
    q: str | None = Query(None, description="Recherche nom/email/téléphone"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            ClientBalanceEvents,
            Users.full_name,
            Users.email,
            Users.phone_e164,
        )
        .join(Users, Users.user_id == ClientBalanceEvents.user_id)
        .order_by(desc(ClientBalanceEvents.occurred_at))
        .offset(offset)
        .limit(limit)
    )

    if user_id:
        stmt = stmt.where(ClientBalanceEvents.user_id == user_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Users.full_name.ilike(pattern),
                Users.email.ilike(pattern),
                Users.phone_e164.ilike(pattern),
            )
        )

    rows = (await db.execute(stmt)).all()
    return [
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
            "occurred_at": ev.occurred_at,
            "created_at": ev.created_at,
        }
        for ev, full_name, email, phone in rows
    ]


@router.get("/users/{user_id}/balance-events")
async def list_user_balance_events(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            ClientBalanceEvents,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == ClientBalanceEvents.user_id)
        .where(ClientBalanceEvents.user_id == user_id)
        .order_by(desc(ClientBalanceEvents.occurred_at))
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
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
        for ev, full_name, email in rows
    ]
