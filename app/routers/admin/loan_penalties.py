from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.loans import Loans
from app.models.loanrepayments import LoanRepayments
from app.services.loan_workflow import outstanding_balance, summarize_installments

router = APIRouter(prefix="/admin/loans", tags=["Admin Loans"])


def _compute_penalty_amount(
    loan: Loans,
    repayments: list[LoanRepayments],
    today: date,
) -> Decimal:
    if not loan.penalty_rate_percent or loan.penalty_rate_percent <= 0:
        return Decimal("0")
    grace = int(loan.grace_days or 0)
    overdue_days = 0
    for inst in repayments:
        if inst.due_date and inst.due_date < today:
            delta = (today - inst.due_date).days - grace
            if delta > overdue_days:
                overdue_days = delta
    if overdue_days <= 0:
        return Decimal("0")
    outstanding = outstanding_balance(repayments)
    daily_rate = Decimal(loan.penalty_rate_percent) / Decimal("100") / Decimal("30")
    return (outstanding * daily_rate * Decimal(overdue_days)).quantize(Decimal("0.01"))


@router.post("/{loan_id}/penalties/recompute")
async def recompute_penalties(
    loan_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    loan: Optional[Loans] = (
        await db.execute(
            select(Loans)
            .options(selectinload(Loans.loan_repayments))
            .where(Loans.loan_id == loan_id)
        )
    ).scalar_one_or_none()
    if not loan:
        raise HTTPException(404, "Pret introuvable.")
    repayments = summarize_installments(loan.loan_repayments or [])
    penalty_amount = _compute_penalty_amount(loan, repayments, date.today())
    if penalty_amount <= 0:
        return {"penalty_applied": False, "message": "Pas de penalite a appliquer."}

    penalty_line = LoanRepayments(
        loan_id=loan.loan_id,
        due_date=date.today(),
        due_amount=penalty_amount,
        paid_amount=Decimal("0"),
    )
    db.add(penalty_line)
    await db.commit()
    await db.refresh(loan)
    return {
        "penalty_applied": True,
        "penalty_amount": float(penalty_amount),
        "loan_id": str(loan.loan_id),
    }
