from decimal import Decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.models.wallets import Wallets
from app.models.wallet_transactions import WalletTransactions

router = APIRouter(prefix="/admin/wallets", tags=["Admin Wallets"])


def compute_alert_label(balance: Decimal) -> str:
    if balance is None:
        return "unknown"
    if balance < Decimal("0"):
        return "critical"
    if balance < Decimal("10000"):
        return "warning"
    return "ok"


@router.get("/")
async def list_wallet_alerts(
    min_available: float = Query(10000.0, description="Inclut les wallets a/bas ce solde"),
    wallet_type: str | None = Query(None, description="Filtre par type de wallet"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            Wallets.wallet_id,
            Wallets.type,
            Wallets.currency_code,
            Wallets.available,
            Wallets.pending,
            Users.user_id,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == Wallets.user_id, isouter=True)
        .where(func.coalesce(Wallets.available, 0) <= min_available)
        .order_by(Wallets.available.asc())
        .limit(limit)
    )

    if wallet_type:
        stmt = stmt.where(Wallets.type == wallet_type)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "wallet_id": str(r.wallet_id),
            "type": r.type,
            "currency": r.currency_code,
            "available": float(r.available or 0),
            "pending": float(r.pending or 0),
            "user_id": str(r.user_id) if r.user_id else None,
            "user_name": r.full_name,
            "user_email": r.email,
            "alert": compute_alert_label(r.available),
        }
        for r in rows
    ]


@router.get("/summary")
async def wallets_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    total_wallets = await db.scalar(select(func.count(Wallets.wallet_id)))
    negative_wallets = await db.scalar(
        select(func.count(Wallets.wallet_id)).where(Wallets.available < 0)
    )
    low_balance_wallets = await db.scalar(
        select(func.count(Wallets.wallet_id)).where(Wallets.available < 10)
    )

    return {
        "total_wallets": total_wallets or 0,
        "negative_wallets": negative_wallets or 0,
        "low_balance_wallets": low_balance_wallets or 0,
    }


@router.get("/{wallet_id}/history")
async def wallet_history_admin(
    wallet_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    wallet = await db.get(Wallets, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet introuvable")

    stmt = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.amount,
            WalletTransactions.direction,
            WalletTransactions.balance_after,
            WalletTransactions.operation_type,
            WalletTransactions.reference,
            WalletTransactions.description,
            WalletTransactions.created_at,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == WalletTransactions.user_id, isouter=True)
        .where(WalletTransactions.wallet_id == wallet_id)
        .order_by(WalletTransactions.created_at.desc())
        .limit(limit)
    )

    if from_date:
        stmt = stmt.where(WalletTransactions.created_at >= from_date)
    if to_date:
        stmt = stmt.where(WalletTransactions.created_at <= to_date)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            WalletTransactions.reference.ilike(pattern)
            | WalletTransactions.operation_type.ilike(pattern)
            | WalletTransactions.description.ilike(pattern)
            | cast(WalletTransactions.amount, String).ilike(pattern)
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "transaction_id": str(r.transaction_id),
            "amount": float(r.amount),
            "direction": r.direction,
            "balance_after": float(r.balance_after),
            "operation_type": r.operation_type,
            "reference": r.reference,
            "description": r.description or "",
            "created_at": r.created_at.isoformat(),
            "user_name": r.full_name,
            "user_email": r.email,
        }
        for r in rows
    ]

