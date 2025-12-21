from typing import Optional
from decimal import Decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.credit_lines import CreditLines
from app.models.credit_line_events import CreditLineEvents
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.wallet_history import log_wallet_movement
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/credit-lines", tags=["Admin Credit Lines"])


@router.get("")
async def list_credit_lines(
    q: Optional[str] = Query(None, description="Filtre nom/email"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            CreditLines.credit_line_id,
            CreditLines.user_id,
            CreditLines.currency_code,
            CreditLines.initial_amount,
            CreditLines.used_amount,
            CreditLines.outstanding_amount,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == CreditLines.user_id)
        .order_by(CreditLines.created_at.desc())
        .limit(limit)
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where((Users.full_name.ilike(pattern)) | (Users.email.ilike(pattern)))

    rows = (await db.execute(stmt)).all()
    return [
        {
            "credit_line_id": str(cl_id),
            "user_id": str(user_id),
            "full_name": full_name,
            "email": email,
            "currency_code": currency,
            "initial_amount": float(initial or 0),
            "used_amount": float(used or 0),
            "outstanding_amount": float(outstanding or 0),
        }
        for cl_id, user_id, currency, initial, used, outstanding, full_name, email in rows
    ]


@router.get("/{credit_line_id}")
async def get_credit_line_detail(
    credit_line_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    credit_line = await db.scalar(
        select(CreditLines).where(CreditLines.credit_line_id == credit_line_id)
    )
    if not credit_line:
        raise HTTPException(404, "Ligne de crédit introuvable")

    user = await db.scalar(select(Users).where(Users.user_id == credit_line.user_id))
    events = (
        await db.execute(
            select(CreditLineEvents)
            .where(CreditLineEvents.credit_line_id == credit_line_id)
            .order_by(CreditLineEvents.created_at.desc())
        )
    ).scalars().all()

    return {
        "credit_line": {
            "credit_line_id": str(credit_line.credit_line_id),
            "user_id": str(credit_line.user_id),
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
            "currency_code": credit_line.currency_code,
            "initial_amount": float(credit_line.initial_amount or 0),
            "used_amount": float(credit_line.used_amount or 0),
            "outstanding_amount": float(credit_line.outstanding_amount or 0),
            "status": credit_line.status,
            "source": credit_line.source,
            "created_at": credit_line.created_at,
            "updated_at": credit_line.updated_at,
        },
        "events": [
            {
                "event_id": str(ev.event_id),
                "amount_delta": float(ev.amount_delta or 0),
                "currency_code": ev.currency_code,
                "old_limit": float(ev.old_limit) if ev.old_limit is not None else None,
                "new_limit": float(ev.new_limit) if ev.new_limit is not None else None,
                "operation_code": ev.operation_code,
                "status": ev.status,
                "source": ev.source,
                "occurred_at": ev.occurred_at,
                "created_at": ev.created_at,
            }
            for ev in events
        ],
    }


class CreditLineIncrease(BaseModel):
    amount: Decimal = Field(..., gt=0)


@router.post("/{credit_line_id}/increase")
async def increase_credit_line(
    credit_line_id: UUID,
    payload: CreditLineIncrease,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    credit_line = await db.scalar(
        select(CreditLines).where(CreditLines.credit_line_id == credit_line_id)
    )
    if not credit_line:
        raise HTTPException(404, "Ligne de crédit introuvable")

    delta = Decimal(payload.amount)
    old_limit = credit_line.initial_amount or Decimal("0")
    credit_line.initial_amount = old_limit + delta
    credit_line.outstanding_amount = (credit_line.outstanding_amount or Decimal("0")) + delta
    credit_line.updated_at = datetime.utcnow()

    event = CreditLineEvents(
        credit_line_id=credit_line.credit_line_id,
        user_id=credit_line.user_id,
        amount_delta=delta,
        currency_code=credit_line.currency_code,
        old_limit=old_limit,
        new_limit=credit_line.initial_amount,
        operation_code=9001,
        status="updated",
        source="admin",
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    await db.commit()

    return await get_credit_line_detail(credit_line_id, db, admin)


class CreditLineRepay(BaseModel):
    amount: Decimal = Field(..., gt=0)


@router.post("/{credit_line_id}/repay")
async def repay_credit_line(
    credit_line_id: UUID,
    payload: CreditLineRepay,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    credit_line = await db.scalar(
        select(CreditLines).where(CreditLines.credit_line_id == credit_line_id)
    )
    if not credit_line:
        raise HTTPException(404, "Ligne de crédit introuvable")

    amount = Decimal(payload.amount)
    old_used = credit_line.used_amount or Decimal("0")
    old_outstanding = credit_line.outstanding_amount or Decimal("0")

    new_used = max(Decimal("0"), old_used - amount)
    new_outstanding = old_outstanding + amount

    credit_line.used_amount = new_used
    credit_line.outstanding_amount = new_outstanding
    credit_line.updated_at = datetime.utcnow()

    movement = None
    if credit_line.currency_code.upper() == "EUR":
        wallet = await db.scalar(
            select(Wallets).where(Wallets.user_id == credit_line.user_id).order_by(Wallets.created_at.asc())
        )
        if not wallet:
            raise HTTPException(404, "Wallet introuvable pour crédit EUR")
        wallet.available = (wallet.available or Decimal("0")) + amount
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=credit_line.user_id,
            amount=amount,
            direction="credit",
            operation_type="credit_line_repay",
            reference=str(credit_line.credit_line_id),
            description="Remboursement ligne de crédit (EUR)",
        )

    event = CreditLineEvents(
        credit_line_id=credit_line.credit_line_id,
        user_id=credit_line.user_id,
        amount_delta=-amount,
        currency_code=credit_line.currency_code,
        old_limit=credit_line.initial_amount,
        new_limit=credit_line.initial_amount,
        operation_code=9002,
        status="repaid",
        source="admin",
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    await db.commit()

    return await get_credit_line_detail(credit_line_id, db, admin)
