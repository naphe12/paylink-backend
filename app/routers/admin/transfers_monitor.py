from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.transactions import Transactions
from app.models.users import Users

EXTERNAL_CHANNELS = {
    "bank_transfer",
    "bank",
    "mobile_money",
    "cash",
    "card",
}

router = APIRouter(prefix="/admin/transfers", tags=["Admin Transfers"])


def serialize_decimal(value: Optional[Decimal]) -> float:
    return float(value or 0)


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
        )
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .where(Transactions.channel != "internal")
        .order_by(Transactions.created_at.desc())
        .limit(limit)
    )

    if channel:
        stmt = stmt.where(Transactions.channel == channel)
    elif channel is None:
        stmt = stmt.where(Transactions.channel.in_(EXTERNAL_CHANNELS))

    if status:
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
        }
        for r in rows
    ]


@router.get("/summary")
async def transfers_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(Transactions.status, func.count(Transactions.tx_id))
        .where(Transactions.channel.in_(EXTERNAL_CHANNELS))
        .group_by(Transactions.status)
    )
    rows = (await db.execute(stmt)).all()
    summary = {status: count for status, count in rows}

    return {
        "pending": summary.get("pending", 0) + summary.get("initiated", 0),
        "failed": summary.get("failed", 0) + summary.get("cancelled", 0),
        "succeeded": summary.get("succeeded", 0),
        "total": sum(summary.values()),
    }
