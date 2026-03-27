from typing import Optional
from decimal import Decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.credit_line_history import CreditLineHistory
from app.models.credit_lines import CreditLines
from app.models.credit_line_events import CreditLineEvents
from app.models.credit_line_payments import CreditLinePayments
from app.models.client_balance_events import ClientBalanceEvents
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.wallet_history import log_wallet_movement
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/credit-lines", tags=["Admin Credit Lines"])


async def _get_latest_credit_line(db: AsyncSession, user_id: UUID):
    return await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
    )


async def _build_debtor_payload(db: AsyncSession, user: Users, wallet: Wallets, credit_line: CreditLines | None):
    wallet_available = Decimal(wallet.available or 0)
    wallet_currency = str(wallet.currency_code or "").upper()
    credit_used = Decimal(credit_line.used_amount or 0) if credit_line else Decimal("0")
    outstanding_amount = Decimal(credit_line.outstanding_amount or 0) if credit_line else Decimal("0")
    origins = []
    if wallet_available < 0:
        origins.append("wallet_negative")
    if credit_used > 0:
        origins.append("credit_line_used")
    if origins == ["wallet_negative", "credit_line_used"]:
        debt_origin_label = "Wallet negatif + credit utilise"
    elif origins == ["wallet_negative"]:
        debt_origin_label = "Wallet negatif"
    elif origins == ["credit_line_used"]:
        debt_origin_label = "Credit utilise"
    else:
        debt_origin_label = "Aucune dette"
    return {
        "user_id": str(user.user_id),
        "full_name": user.full_name,
        "email": user.email,
        "wallet_id": str(wallet.wallet_id),
        "wallet_currency": wallet_currency,
        "wallet_available": float(wallet_available),
        "wallet_negative_amount": float(abs(wallet_available)) if wallet_available < 0 else 0.0,
        "credit_line_id": str(credit_line.credit_line_id) if credit_line else None,
        "credit_line_currency": str(credit_line.currency_code or "").upper() if credit_line else None,
        "credit_used": float(credit_used),
        "credit_due": float(credit_used),
        "credit_available": float(outstanding_amount),
        "has_credit_line": bool(credit_line),
        "is_wallet_negative": wallet_available < 0,
        "debt_origins": origins,
        "debt_origin_label": debt_origin_label,
    }


@router.get("/debtors")
async def list_credit_debtors(
    q: Optional[str] = Query(None, description="Filtre nom/email"),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(Users, Wallets)
        .join(Wallets, Wallets.user_id == Users.user_id)
        .order_by(Users.full_name.asc())
        .limit(limit)
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where((Users.full_name.ilike(pattern)) | (Users.email.ilike(pattern)))

    rows = (await db.execute(stmt)).all()
    items = []
    for user, wallet in rows:
        credit_line = await _get_latest_credit_line(db, user.user_id)
        wallet_available = Decimal(wallet.available or 0)
        credit_used = Decimal(credit_line.used_amount or 0) if credit_line else Decimal("0")
        if wallet_available < 0 or credit_used > 0:
            items.append(await _build_debtor_payload(db, user, wallet, credit_line))
    return items


@router.get("")
async def list_credit_lines(
    q: Optional[str] = Query(None, description="Filtre nom/email"),
    user_id: UUID | None = Query(None),
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
    if user_id:
        stmt = stmt.where(CreditLines.user_id == user_id)

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


class CreditLineCreate(BaseModel):
    user_id: UUID
    amount: Decimal = Field(..., gt=0)
    currency_code: str = Field(default="EUR", min_length=3, max_length=3)


@router.post("")
async def create_credit_line(
    payload: CreditLineCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    existing = await db.scalar(
        select(CreditLines).where(CreditLines.user_id == payload.user_id)
    )
    if existing:
        raise HTTPException(400, "Une ligne de credit existe deja pour cet utilisateur.")

    amount = Decimal(payload.amount)
    currency_code = payload.currency_code.upper()
    now = datetime.utcnow()
    credit_line = CreditLines(
        user_id=payload.user_id,
        currency_code=currency_code,
        initial_amount=amount,
        used_amount=Decimal("0"),
        outstanding_amount=amount,
        status="active",
        source="admin",
        created_at=now,
        updated_at=now,
    )
    db.add(credit_line)
    await db.flush()

    user.credit_limit = amount
    user.credit_used = Decimal("0")

    db.add(
        CreditLineEvents(
            credit_line_id=credit_line.credit_line_id,
            user_id=payload.user_id,
            amount_delta=amount,
            currency_code=currency_code,
            old_limit=Decimal("0"),
            new_limit=amount,
            operation_code=9000,
            status="created",
            source="admin",
            occurred_at=now,
        )
    )
    db.add(
        CreditLineHistory(
            user_id=payload.user_id,
            transaction_id=None,
            amount=amount,
            credit_available_before=Decimal("0"),
            credit_available_after=amount,
            description="Augmentation de ligne de credit",
        )
    )
    await db.commit()

    return await get_credit_line_detail(credit_line.credit_line_id, db, admin)


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
    old_outstanding = credit_line.outstanding_amount or Decimal("0")
    credit_line.initial_amount = old_limit + delta
    new_outstanding = old_outstanding + delta
    credit_line.outstanding_amount = new_outstanding
    credit_line.updated_at = datetime.utcnow()

    user = await db.scalar(select(Users).where(Users.user_id == credit_line.user_id))
    if user:
        user.credit_limit = credit_line.initial_amount
        user.credit_used = credit_line.used_amount or Decimal("0")

    event = CreditLineEvents(
        credit_line_id=credit_line.credit_line_id,
        user_id=credit_line.user_id,
        amount_delta=delta,
        currency_code=credit_line.currency_code,
        old_limit=old_outstanding,
        new_limit=new_outstanding,
        operation_code=9001,
        status="updated",
        source="admin",
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    db.add(
        CreditLineHistory(
            user_id=credit_line.user_id,
            transaction_id=None,
            amount=delta,
            credit_available_before=old_outstanding,
            credit_available_after=new_outstanding,
            description="Augmentation de ligne de credit",
        )
    )
    await db.commit()

    return await get_credit_line_detail(credit_line_id, db, admin)


class CreditLineDecrease(BaseModel):
    amount: Decimal = Field(..., gt=0)


@router.post("/{credit_line_id}/decrease")
async def decrease_credit_line(
    credit_line_id: UUID,
    payload: CreditLineDecrease,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    credit_line = await db.scalar(
        select(CreditLines).where(CreditLines.credit_line_id == credit_line_id)
    )
    if not credit_line:
        raise HTTPException(404, "Ligne de credit introuvable")

    amount = Decimal(payload.amount)
    old_limit = credit_line.initial_amount or Decimal("0")
    old_outstanding = credit_line.outstanding_amount or Decimal("0")
    used_amount = credit_line.used_amount or Decimal("0")
    new_limit = old_limit - amount
    if new_limit < used_amount:
        raise HTTPException(
            400,
            "Reduction impossible: le nouveau plafond serait inferieur au credit deja utilise.",
        )

    new_outstanding = max(Decimal("0"), old_outstanding - amount)
    credit_line.initial_amount = new_limit
    credit_line.outstanding_amount = new_outstanding
    credit_line.updated_at = datetime.utcnow()

    user = await db.scalar(select(Users).where(Users.user_id == credit_line.user_id))
    if user:
        user.credit_limit = credit_line.initial_amount
        user.credit_used = credit_line.used_amount or Decimal("0")

    db.add(
        CreditLineEvents(
            credit_line_id=credit_line.credit_line_id,
            user_id=credit_line.user_id,
            amount_delta=-amount,
            currency_code=credit_line.currency_code,
            old_limit=old_outstanding,
            new_limit=new_outstanding,
            operation_code=9003,
            status="decreased",
            source="admin",
            occurred_at=datetime.utcnow(),
        )
    )
    db.add(
        CreditLineHistory(
            user_id=credit_line.user_id,
            transaction_id=None,
            amount=-amount,
            credit_available_before=old_outstanding,
            credit_available_after=new_outstanding,
            description="Diminution de ligne de credit",
        )
    )
    await db.commit()

    return await get_credit_line_detail(credit_line_id, db, admin)


class CreditLineRepay(BaseModel):
    amount: Decimal = Field(..., gt=0)


@router.post("/users/{user_id}/repay")
async def repay_client_debt(
    user_id: UUID,
    payload: CreditLineRepay,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    if not wallet:
        raise HTTPException(404, "Wallet introuvable")

    credit_line = await _get_latest_credit_line(db, user_id)
    amount = Decimal(payload.amount)
    wallet_currency = str(wallet.currency_code or "").upper()
    wallet_before = Decimal(wallet.available or 0)
    wallet_delta = amount if (wallet_currency == "EUR" or credit_line is None) else Decimal("0")
    wallet_after = wallet_before + wallet_delta

    if credit_line is None and wallet_before >= 0:
        raise HTTPException(400, "Aucune dette a rembourser pour cet utilisateur.")
    if credit_line is not None and Decimal(credit_line.used_amount or 0) <= 0 and wallet_before >= 0:
        raise HTTPException(400, "Aucune dette a rembourser pour cet utilisateur.")

    applied_to_credit = Decimal("0")
    if credit_line is not None:
        old_used = Decimal(credit_line.used_amount or 0)
        old_outstanding = Decimal(credit_line.outstanding_amount or 0)
        applied_to_credit = min(amount, old_used)
        credit_line.used_amount = max(Decimal("0"), old_used - applied_to_credit)
        credit_line.outstanding_amount = old_outstanding + applied_to_credit
        credit_line.updated_at = datetime.utcnow()

        user.credit_limit = Decimal(credit_line.initial_amount or 0)
        user.credit_used = Decimal(credit_line.used_amount or 0)

        db.add(
            CreditLinePayments(
                credit_line_id=credit_line.credit_line_id,
                user_id=user_id,
                amount=applied_to_credit,
                currency_code=credit_line.currency_code,
                amount_eur=amount if wallet_currency == "EUR" else None,
                balance_before=old_outstanding,
                balance_after=Decimal(credit_line.outstanding_amount or 0),
                occurred_at=datetime.utcnow(),
            )
        )
        db.add(
            CreditLineEvents(
                credit_line_id=credit_line.credit_line_id,
                user_id=user_id,
                amount_delta=-applied_to_credit,
                currency_code=credit_line.currency_code,
                old_limit=old_outstanding,
                new_limit=Decimal(credit_line.outstanding_amount or 0),
                operation_code=9002,
                status="completed",
                source="admin_repayment",
                occurred_at=datetime.utcnow(),
            )
        )
        db.add(
            CreditLineHistory(
                user_id=user_id,
                transaction_id=None,
                amount=-applied_to_credit,
                credit_available_before=old_outstanding,
                credit_available_after=Decimal(credit_line.outstanding_amount or 0),
                description="Remboursement admin de dette client",
            )
        )

    wallet.available = wallet_after
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=user_id,
        amount=wallet_delta,
        direction="credit",
        operation_type="admin_client_debt_repayment",
        reference=str(getattr(credit_line, "credit_line_id", user_id)),
        description="Remboursement admin dette client",
    )
    if wallet_delta == 0:
        db.add(
            ClientBalanceEvents(
                user_id=user_id,
                balance_before=wallet_before,
                balance_after=wallet_after,
                amount_delta=Decimal("0"),
                source="admin_client_debt_repayment",
                occurred_at=datetime.utcnow(),
                currency=wallet.currency_code,
            )
        )

    await db.commit()

    return {
        "message": "Remboursement enregistre",
        "movement_id": str(movement.transaction_id) if movement else None,
        "debtor": await _build_debtor_payload(db, user, wallet, credit_line),
    }


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

    user = await db.scalar(select(Users).where(Users.user_id == credit_line.user_id))
    if user:
        user.credit_limit = credit_line.initial_amount or Decimal("0")
        user.credit_used = new_used

    movement = None
    if credit_line.currency_code.upper() == "EUR":
        wallet = await db.scalar(
            select(Wallets).where(Wallets.user_id == credit_line.user_id)
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
        old_limit=old_outstanding,
        new_limit=new_outstanding,
        operation_code=9002,
        status="completed",
        source="admin",
        occurred_at=datetime.utcnow(),
    )
    db.add(event)
    db.add(
        CreditLineHistory(
            user_id=credit_line.user_id,
            transaction_id=None,
            amount=-amount,
            credit_available_before=old_outstanding,
            credit_available_after=new_outstanding,
            description="Remboursement ligne de credit",
        )
    )
    await db.commit()

    return await get_credit_line_detail(credit_line_id, db, admin)
