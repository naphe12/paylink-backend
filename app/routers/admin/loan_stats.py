from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select, text
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


# Liste des prêts (admin) - accepte /admin/loans et /admin/loans/
@router.get("", response_model=list[LoanAdminItem])
@router.get("/", response_model=list[LoanAdminItem])
async def list_loans_admin(
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    product_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    print(f"[admin/loans] status={status} overdue_only={overdue_only} limit={limit}")
    stmt = (
        select(Loans)
        .options(selectinload(Loans.loan_repayments), selectinload(Loans.users))
        .order_by(Loans.created_at.desc())
        .limit(min(limit, 200))
        .offset(max(offset, 0))
    )
    if status:
        stmt = stmt.where(Loans.status == status)
    if product_type:
        stmt = stmt.where(Loans.product_type == product_type)

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
                product_type=getattr(loan, "product_type", None),
                product_id=str(getattr(loan, "product_id", "")) if getattr(loan, "product_id", None) else None,
                business_name=getattr(loan, "business_name", None),
            )
        )
    return response


@router.get("/list", response_model=list[LoanAdminItem])
async def list_loans_admin_alias(
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    product_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    return await list_loans_admin(status, overdue_only, limit, offset, product_type, db, _)


@router.post("/{loan_id}/approve")
async def approve_loan(
    loan_id: str,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    loan = await db.get(Loans, loan_id)
    if not loan:
        raise HTTPException(404, "Credit introuvable.")
    if loan.status != "draft":
        raise HTTPException(400, "Ce credit n'est pas en attente (draft).")

    if loan.product_id:
        prod = (
            await db.execute(
                text("SELECT require_documents FROM paylink.loan_products WHERE product_id = :pid"),
                {"pid": str(loan.product_id)},
            )
        ).mappings().first()
        require_docs = prod["require_documents"] if prod else False
        docs_status = (loan.metadata_ or {}).get("documents_status")
        docs_payload = (loan.metadata_ or {}).get("documents") or []
        if require_docs and not docs_payload:
            raise HTTPException(400, "Documents requis manquants pour ce pret.")
        if require_docs and docs_status != "approved":
            raise HTTPException(400, "Documents requis non valides pour ce pret.")

    loan.status = "active"
    loan.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Credit valide", "loan_id": str(loan.loan_id), "status": loan.status}
