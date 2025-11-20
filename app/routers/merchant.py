from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.invoices import Invoices
from app.models.merchants import Merchants
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/merchant", tags=["Merchant"])


class SettlementRequest(BaseModel):
    amount: Decimal = Field(gt=0)


async def _get_merchant(
    db: AsyncSession, current_user: Users
) -> tuple[Merchants, Wallets]:
    merchant = await db.scalar(
        select(Merchants).where(Merchants.user_id == current_user.user_id)
    )
    if not merchant:
        raise HTTPException(403, "Accès réservé aux marchands")

    wallet = None
    if merchant.settlement_wallet:
        wallet = await db.get(Wallets, merchant.settlement_wallet)
    if wallet is None:
        wallet = await db.scalar(
            select(Wallets).where(
                Wallets.user_id == current_user.user_id,
                Wallets.type.in_(["merchant", "settlement"]),
            )
        )
    if wallet is None:
        raise HTTPException(404, "Wallet marchand introuvable")
    return merchant, wallet


@router.get("/dashboard")
async def merchant_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    merchant, wallet = await _get_merchant(db, current_user)

    total_paid = await db.scalar(
        select(func.coalesce(func.sum(Invoices.amount), 0)).where(
            Invoices.merchant_id == merchant.merchant_id,
            Invoices.status == "paid",
        )
    )

    pending_invoices = await db.scalar(
        select(func.count(Invoices.invoice_id)).where(
            Invoices.merchant_id == merchant.merchant_id,
            Invoices.status == "unpaid",
        )
    )

    week_ago = datetime.utcnow() - timedelta(days=6)
    daily_stmt = (
        select(
            func.date_trunc("day", Invoices.created_at).label("bucket"),
            func.sum(
                case(
                    (Invoices.status == "paid", Invoices.amount),
                    else_=0,
                )
            ).label("amount"),
        )
        .where(
            Invoices.created_at >= week_ago,
            Invoices.merchant_id == merchant.merchant_id,
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    daily_rows = (await db.execute(daily_stmt)).all()

    recent_stmt = (
        select(Invoices)
        .where(Invoices.merchant_id == merchant.merchant_id)
        .order_by(Invoices.created_at.desc())
        .limit(10)
    )
    recent = (await db.execute(recent_stmt)).scalars().all()

    return {
        "wallet_balance": float(wallet.available or 0),
        "total_payments": float(total_paid or 0),
        "pending_invoices": pending_invoices or 0,
        "daily_volume": [
            {"date": row.bucket.date().isoformat(), "amount": float(row.amount or 0)}
            for row in daily_rows
        ],
        "recent_invoices": [
            {
                "invoice_id": str(inv.invoice_id),
                "amount": float(inv.amount),
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in recent
        ],
    }


@router.post("/settlements")
async def settle_merchant_funds(
    payload: SettlementRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    merchant, wallet = await _get_merchant(db, current_user)

    if wallet.available < payload.amount:
        raise HTTPException(400, "Solde insuffisant pour le versement")

    # Trouver le wallet cible (ex: compte principal PayLink)
    settlement_wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == current_user.user_id,
            Wallets.type == "settlement",
        )
    )
    if not settlement_wallet:
        raise HTTPException(404, "Wallet de règlement introuvable")

    wallet.available -= payload.amount
    settlement_wallet.available += payload.amount
    await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=payload.amount,
        direction="debit",
        operation_type="merchant_settlement",
        reference=str(merchant.merchant_id),
        description="Virement vers compte de règlement",
    )
    await log_wallet_movement(
        db,
        wallet=settlement_wallet,
        user_id=current_user.user_id,
        amount=payload.amount,
        direction="credit",
        operation_type="merchant_settlement_receive",
        reference=str(merchant.merchant_id),
        description="Crédit règlement marchand",
    )

    tx = Transactions(
        amount=payload.amount,
        currency_code=wallet.currency_code,
        channel="internal",
        status="succeeded",
        sender_wallet=wallet.wallet_id,
        receiver_wallet=settlement_wallet.wallet_id,
        initiated_by=current_user.user_id,
        description=f"Merchant settlement {merchant.legal_name}",
    )
    db.add(tx)

    await db.commit()
    return {
        "message": "Versement effectué",
        "transaction_id": str(tx.tx_id),
        "new_balance": float(wallet.available),
    }


@router.get("/payments")
async def merchant_payments(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    merchant, _ = await _get_merchant(db, current_user)

    stmt = (
        select(Invoices)
        .where(Invoices.merchant_id == merchant.merchant_id)
        .order_by(Invoices.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Invoices.status == status)

    invoices = (await db.execute(stmt)).scalars().all()

    return [
        {
            "invoice_id": str(inv.invoice_id),
            "amount": float(inv.amount),
            "currency": inv.currency_code,
            "status": inv.status,
            "created_at": inv.created_at.isoformat(),
            "updated_at": inv.updated_at.isoformat(),
        }
        for inv in invoices
    ]
