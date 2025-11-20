from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.core.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.aml import update_risk_score
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/agent", tags=["Agent Operations"])


@router.post("/cash-in")
async def agent_cash_in(
    client_phone: str,
    amount: Decimal,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_agent)
):
    # ✅ Trouver client
    client = await db.scalar(select(Users).where(Users.phone_e164 == client_phone))
    if not client:
        raise HTTPException(404, "Client introuvable")

    # ✅ Récupérer wallets
    agent_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == agent.user_id))
    client_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == client.user_id))

    # ✅ Créditer client
    client_wallet.available += amount
    await log_wallet_movement(
        db,
        wallet=client_wallet,
        user_id=client.user_id,
        amount=amount,
        direction="credit",
        operation_type="agent_cash_in",
        reference=agent.phone_e164,
        description=f"Cash-in agent {agent.full_name}",
    )

    # ✅ Commission agent (1.5%)
    commission = amount * Decimal("0.015")
    agent_wallet.available += commission
    await log_wallet_movement(
        db,
        wallet=agent_wallet,
        user_id=agent.user_id,
        amount=commission,
        direction="credit",
        operation_type="agent_commission",
        reference=str(client.user_id),
        description=f"Commission cash-in client {client.full_name}",
    )

    # ✅ AML
    await update_risk_score(db, client)

    await db.commit()
    return {"message": "✅ Cash-in effectué", "commission": float(commission)}


@router.post("/cash-out")
async def agent_cash_out(
    client_phone: str,
    amount: Decimal,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_agent)
):
    # ✅ Trouver client
    client = await db.scalar(select(Users).where(Users.phone_e164 == client_phone))
    if not client:
        raise HTTPException(404, "Client introuvable")

    # ✅ Récupérer wallets
    agent_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == agent.user_id))
    client_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == client.user_id))

    # ✅ Vérifier solde
    if client_wallet.available < amount:
        raise HTTPException(400, "Solde client insuffisant")

    # ✅ Débiter client
    client_wallet.available -= amount
    await log_wallet_movement(
        db,
        wallet=client_wallet,
        user_id=client.user_id,
        amount=amount,
        direction="debit",
        operation_type="agent_cash_out",
        reference=agent.phone_e164,
        description=f"Cash-out agent {agent.full_name}",
    )

    # ✅ Commission agent (2%)
    commission = amount * Decimal("0.02")
    agent_wallet.available += commission
    await log_wallet_movement(
        db,
        wallet=agent_wallet,
        user_id=agent.user_id,
        amount=commission,
        direction="credit",
        operation_type="agent_commission",
        reference=str(client.user_id),
        description=f"Commission cash-out client {client.full_name}",
    )

    # ✅ AML
    await update_risk_score(db, client)

    await db.commit()
    return {"message": "✅ Cash-out effectué", "commission": float(commission)}
