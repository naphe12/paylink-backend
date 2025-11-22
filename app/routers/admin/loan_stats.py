from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.loanrepayments import LoanRepayments
from app.models.loans import Loans
from app.routers.loans import LoanAdminItem
from app.services.loan_workflow import has_overdue_installments, outstanding_balance

router = APIRouter(prefix="/admin/loans", tags=["Admin Loans"])


@router.get("/stats")
async def loan_statistics(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)

    loan_counts_stmt = select(
        func.count(Loans.loan_id).label("total"),
        func.sum(case((Loans.status == "active", 1), else_=0)).label("active"),
        func.sum(case((Loans.status == "in_arrears", 1), else_=0)).label("arrears"),
        func.sum(case((Loans.status == "repaid", 1), else_=0)).label("repaid"),
    )
    loan_counts = (await db.execute(loan_counts_stmt)).one()

    outstanding_stmt = (
        select(
            func.coalesce(
                func.sum(
                    LoanRepayments.due_amount - func.coalesce(LoanRepayments.paid_amount, 0)
                ),
                0,
            ).label("outstanding")
        )
        .join(Loans, LoanRepayments.loan_id == Loans.loan_id)
        .where(Loans.status.in_(("draft", "active", "in_arrears")))
    )
    outstanding = await db.scalar(outstanding_stmt)

    overdue_stmt = select(func.count(LoanRepayments.repayment_id)).where(
        LoanRepayments.due_date < now.date(),
        func.coalesce(LoanRepayments.paid_amount, 0)
        < func.coalesce(LoanRepayments.due_amount, 0),
    )
    overdue = await db.scalar(overdue_stmt)

    recent_stmt = select(
        func.coalesce(func.sum(LoanRepayments.paid_amount), 0)
    ).where(LoanRepayments.paid_at >= month_ago)
    recent_repayments = await db.scalar(recent_stmt)

    total_installments = await db.scalar(select(func.count(LoanRepayments.repayment_id)))
    paid_installments = await db.scalar(
        select(func.count(LoanRepayments.repayment_id)).where(
            LoanRepayments.paid_amount >= LoanRepayments.due_amount,
            LoanRepayments.due_amount > 0,
        )
    )
    repayment_rate = (
        float(paid_installments) / float(total_installments)
        if total_installments
        else 0.0
    )

    return {
        "loans": {
            "total": loan_counts.total or 0,
            "active": loan_counts.active or 0,
            "in_arrears": loan_counts.arrears or 0,
            "repaid": loan_counts.repaid or 0,
        },
        "outstanding_balance": float(outstanding or 0),
        "overdue_installments": overdue or 0,
        "repaid_last_30d": float(recent_repayments or 0),
        "repayment_rate": repayment_rate,
    }


@router.get("/", response_model=list[LoanAdminItem])
async def list_loans_admin(
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    stmt = (
        select(Loans)
        .options(selectinload(Loans.loan_repayments), selectinload(Loans.users))
        .order_by(Loans.created_at.desc())
        .limit(min(limit, 200))
    )
    if status:
        stmt = stmt.where(Loans.status == status)

    rows = (await db.execute(stmt)).scalars().all()
    response: list[LoanAdminItem] = []
    for loan in rows:
        overdue = has_overdue_installments(loan.loan_repayments or [])
        if overdue_only and not overdue:
            continue
        response.append(
            LoanAdminItem(
                loan_id=str(loan.loan_id),
                borrower_id=str(loan.borrower_user),
                borrower_name=getattr(loan.users, "full_name", None),
                borrower_email=getattr(loan.users, "email", None),
                status=loan.status,
                principal=loan.principal,
                currency_code=loan.currency_code,
                risk_level=loan.risk_level,
                created_at=loan.created_at,
                outstanding_balance=outstanding_balance(loan.loan_repayments or []),
                overdue=overdue,
            )
        )
    return response
