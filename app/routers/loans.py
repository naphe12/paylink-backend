from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.dependencies.auth import get_current_admin
from app.models.notifications import Notifications
from app.models.loanrepayments import LoanRepayments
from app.models.loans import Loans
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.loan_workflow import (
    build_repayment_schedule,
    has_overdue_installments,
    map_score_to_risk,
    outstanding_balance,
    summarize_installments,
    next_due_installment,
)
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/loans", tags=["Loans"])

def _row_to_product(row) -> dict:
    return {
        "product_id": str(row["product_id"]),
        "name": row["name"],
        "product_type": row["product_type"],
        "min_principal": float(row["min_principal"]),
        "max_principal": float(row["max_principal"]),
        "term_min_months": row["term_min_months"],
        "term_max_months": row["term_max_months"],
        "apr_percent": float(row["apr_percent"]),
        "fee_flat": float(row["fee_flat"]) if row["fee_flat"] is not None else None,
        "fee_percent": float(row["fee_percent"]) if row["fee_percent"] is not None else None,
        "penalty_rate_percent": float(row["penalty_rate_percent"]) if row["penalty_rate_percent"] is not None else None,
        "grace_days": row["grace_days"],
        "require_documents": bool(row["require_documents"]),
        "metadata": row["metadata"],
    }


class LoanApplicationPayload(BaseModel):
    principal: Decimal = Field(..., gt=0)
    currency_code: str = Field(..., min_length=3, max_length=3)
    term_months: int = Field(..., ge=1, le=12)
    apr_percent: Decimal | None = Field(default=Decimal("12.0"), gt=0)
    product_id: uuid.UUID | None = None
    product_type: Literal["consumer", "business"] | None = None
    business_name: str | None = None
    business_activity: str | None = None
    monthly_revenue: Decimal | None = None
    documents: list[dict] | None = None


class LoanDecisionResponse(BaseModel):
    loan_id: str
    decision: Literal["pending", "approved", "rejected"]
    risk_level: str
    score: int
    reason: str | None = None


class LoanDisbursementResponse(BaseModel):
    loan_id: str
    status: str
    credited_amount: Decimal
    wallet_id: str


class LoanRepaymentPayload(BaseModel):
    amount: Decimal = Field(..., gt=0)


class InstallmentRead(BaseModel):
    repayment_id: str
    due_date: date
    due_amount: Decimal
    paid_amount: Decimal | None
    paid_at: datetime | None


class LoanDetail(BaseModel):
    loan_id: str
    status: str
    principal: Decimal
    currency_code: str
    apr_percent: Decimal
    term_months: int
    created_at: datetime
    risk_level: str | None
    outstanding_balance: Decimal
    overdue: bool
    product_type: str | None = None
    product_id: str | None = None
    business_name: str | None = None
    business_activity: str | None = None
    monthly_revenue: Decimal | None = None
    installments: list[InstallmentRead]


class LoanPortfolio(BaseModel):
    credit_limit: Decimal
    credit_used: Decimal
    available_credit: Decimal
    risk_score: int
    loans: list[LoanDetail]


class LoanAdminItem(BaseModel):
    loan_id: str
    borrower_id: str
    borrower_name: str | None
    borrower_email: str | None
    status: str
    principal: Decimal
    currency_code: str
    risk_level: str | None
    created_at: datetime
    outstanding_balance: Decimal
    overdue: bool
    product_type: str | None = None
    product_id: str | None = None
    business_name: str | None = None


class LoanAdminList(BaseModel):
    total: int
    items: list[LoanAdminItem]


class LoanReminderPayload(BaseModel):
    message: str | None = None


class LoanReminderResponse(BaseModel):
    loan_id: str
    reminder_sent: bool
    overdue_installments: int
    message: str


@router.get("/products")
async def list_loan_products(
    product_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    params = {}
    sql = "SELECT * FROM paylink.loan_products"
    if product_type:
        sql += " WHERE product_type = :ptype"
        params["ptype"] = product_type
    sql += " ORDER BY created_at DESC"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return [_row_to_product(r) for r in rows]


def _ensure_active_user(user: Users):
    if user.status != "active":
        raise HTTPException(403, "Compte inactif : demande de crédit impossible.")
    # Autorise temporairement unverified
    if getattr(user, "kyc_status", None) not in {"verified", "reviewing", "unverified"}:
        raise HTTPException(403, "KYC requis avant de demander un crédit.")


@router.post("/apply", response_model=LoanDecisionResponse)
async def apply_for_short_term_loan(
    payload: LoanApplicationPayload,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    _ensure_active_user(current_user)

    product = None
    if payload.product_id:
        product_row = (
            await db.execute(
                text("SELECT * FROM paylink.loan_products WHERE product_id = :pid"),
                {"pid": str(payload.product_id)},
            )
        ).mappings().first()
        if not product_row:
            raise HTTPException(404, "Produit de crédit introuvable.")
        product = product_row

    product_type = payload.product_type or (product["product_type"] if product else None) or "consumer"
    if product and product["product_type"] != product_type:
        raise HTTPException(400, "Type de produit incohérent.")

    active_stmt = select(func.count(Loans.loan_id)).where(
        Loans.borrower_user == current_user.user_id,
        Loans.status.in_(("draft", "active", "in_arrears")),
    )
    active_count = await db.scalar(active_stmt)
    if active_count:
        raise HTTPException(400, "Un crédit est déjà en cours pour cet utilisateur.")

    available = Decimal(current_user.credit_limit or 0) - Decimal(current_user.credit_used or 0)
    if payload.principal > available:
        raise HTTPException(400, "Montant demandé supérieur au plafond disponible.")

    if product:
        if payload.principal < Decimal(product["min_principal"]) or payload.principal > Decimal(product["max_principal"]):
            raise HTTPException(400, "Montant hors des limites du produit.")
        if payload.term_months < int(product["term_min_months"]) or payload.term_months > int(product["term_max_months"]):
            raise HTTPException(400, "Duree hors des limites du produit.")
        payload.apr_percent = Decimal(product["apr_percent"])
        if product.get("require_documents") and not payload.documents:
            raise HTTPException(400, "Documents requis pour ce produit.")

    if product_type == "business":
        if not payload.business_name and not payload.business_activity:
            raise HTTPException(400, "Renseignez au moins le nom ou l'activite de l'entreprise.")

    risk_level = map_score_to_risk(current_user.risk_score)
    loan = Loans(
        borrower_user=current_user.user_id,
        principal=payload.principal,
        currency_code=payload.currency_code.upper(),
        apr_percent=payload.apr_percent or Decimal("12.0"),
        term_months=payload.term_months,
        status="draft",
        risk_level=risk_level,
        product_type=product_type,
        product_id=str(payload.product_id) if payload.product_id else None,
        business_name=payload.business_name,
        business_activity=payload.business_activity,
        monthly_revenue=payload.monthly_revenue,
        penalty_rate_percent=Decimal(product["penalty_rate_percent"] or 0) if product else None,
        grace_days=int(product["grace_days"]) if product else None,
        metadata_=({"documents": payload.documents} if payload.documents else None),
    )
    db.add(loan)
    await db.commit()
    await db.refresh(loan)

    return LoanDecisionResponse(
        loan_id=str(loan.loan_id),
        decision="pending",
        risk_level=risk_level,
        score=current_user.risk_score or 0,
        reason="Demande enregistrée. En attente d'analyse."
    )


@router.get("/me", response_model=LoanPortfolio)
async def get_my_loans(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    loans = (
        await db.execute(
            select(Loans)
            .where(Loans.borrower_user == current_user.user_id)
            .options(selectinload(Loans.loan_repayments))
            .order_by(Loans.created_at.desc())
        )
    ).scalars().all()

    loan_payload: list[LoanDetail] = []
    for loan in loans:
        installments = [
            InstallmentRead(
                repayment_id=str(inst.repayment_id),
                due_date=inst.due_date,
                due_amount=Decimal(inst.due_amount or 0),
                paid_amount=Decimal(inst.paid_amount or 0),
                paid_at=inst.paid_at,
            )
            for inst in summarize_installments(loan.loan_repayments or [])
        ]
        loan_payload.append(
            LoanDetail(
                loan_id=str(loan.loan_id),
                status=loan.status,
                principal=loan.principal,
                currency_code=loan.currency_code,
                apr_percent=loan.apr_percent,
                term_months=loan.term_months,
                created_at=loan.created_at,
                risk_level=loan.risk_level,
                outstanding_balance=outstanding_balance(loan.loan_repayments or []),
                overdue=has_overdue_installments(loan.loan_repayments or []),
                product_type=getattr(loan, "product_type", None),
                product_id=str(getattr(loan, "product_id", "")) if getattr(loan, "product_id", None) else None,
                business_name=getattr(loan, "business_name", None),
                business_activity=getattr(loan, "business_activity", None),
                monthly_revenue=getattr(loan, "monthly_revenue", None),
                installments=installments,
            )
        )

    credit_limit = Decimal(current_user.credit_limit or 0)
    credit_used = Decimal(current_user.credit_used or 0)
    available_credit = max(Decimal("0"), credit_limit - credit_used)

    return LoanPortfolio(
        credit_limit=credit_limit,
        credit_used=credit_used,
        available_credit=available_credit,
        risk_score=current_user.risk_score or 0,
        loans=loan_payload,
    )


@router.post("/{loan_id}/analyze", response_model=LoanDecisionResponse)
async def analyze_and_accept_loan(
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    loan = await db.get(Loans, loan_id)
    if not loan:
        raise HTTPException(404, "Crédit introuvable.")
    if loan.status != "draft":
        raise HTTPException(400, "Ce crédit a déjà été traité.")

    borrower = await db.get(Users, loan.borrower_user)
    if not borrower:
        raise HTTPException(404, "Emprunteur introuvable.")

    risk_level = map_score_to_risk(borrower.risk_score)
    available = Decimal(borrower.credit_limit or 0) - Decimal(borrower.credit_used or 0)

    decision = "approved"
    reason = None

    if risk_level in {"high", "critical"}:
        decision = "rejected"
        reason = "Profil risque élevé"
    elif loan.principal > available:
        decision = "rejected"
        reason = "Plafond de crédit insuffisant"

    if decision == "rejected":
        loan.status = "written_off"
        loan.risk_level = risk_level
        await db.commit()
        return LoanDecisionResponse(
            loan_id=str(loan.loan_id),
            decision="rejected",
            risk_level=risk_level,
            score=borrower.risk_score or 0,
            reason=reason,
        )

    await db.execute(delete(LoanRepayments).where(LoanRepayments.loan_id == loan.loan_id))
    schedule = build_repayment_schedule(
        Decimal(loan.principal), Decimal(loan.apr_percent), loan.term_months
    )
    for due_date, due_amount in schedule:
        db.add(
            LoanRepayments(
                loan_id=loan.loan_id,
                due_date=due_date,
                due_amount=due_amount,
                paid_amount=Decimal("0"),
            )
        )

    loan.risk_level = risk_level
    await db.commit()

    return LoanDecisionResponse(
        loan_id=str(loan.loan_id),
        decision="approved",
        risk_level=risk_level,
        score=borrower.risk_score or 0,
        reason=None,
    )


@router.post("/{loan_id}/disburse", response_model=LoanDisbursementResponse)
async def disburse_loan(
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    loan = await db.get(Loans, loan_id)
    if not loan:
        raise HTTPException(404, "Crédit introuvable.")
    if loan.status not in {"draft"}:
        raise HTTPException(400, "Crédit déjà débloqué.")

    if loan.product_id:
        prod_row = (
            await db.execute(
                text("SELECT require_documents FROM paylink.loan_products WHERE product_id = :pid"),
                {"pid": str(loan.product_id)},
            )
        ).mappings().first()
        require_docs = prod_row["require_documents"] if prod_row else False
        docs_status = (loan.metadata_ or {}).get("documents_status")
        docs_payload = (loan.metadata_ or {}).get("documents") or []
        if require_docs and not docs_payload:
            raise HTTPException(400, "Documents requis manquants pour ce prêt.")
        if require_docs and docs_status != "approved":
            raise HTTPException(400, "Documents requis non valides pour ce prêt.")

    installments = (
        await db.execute(
            select(LoanRepayments).where(LoanRepayments.loan_id == loan.loan_id)
        )
    ).scalars().all()
    if not installments:
        raise HTTPException(400, "Ce crédit n'a pas encore été approuvé.")

    borrower = await db.get(Users, loan.borrower_user)
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == borrower.user_id))
    if not wallet:
        raise HTTPException(404, "Portefeuille indisponible pour ce client.")

    available = Decimal(borrower.credit_limit or 0) - Decimal(borrower.credit_used or 0)
    if Decimal(loan.principal) > available:
        raise HTTPException(400, "Plafond de crédit insuffisant.")

    wallet.available = Decimal(wallet.available or 0) + Decimal(loan.principal)
    await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=borrower.user_id,
        amount=loan.principal,
        direction="credit",
        operation_type="loan_disbursement",
        reference=str(loan.loan_id),
        description="Déblocage du crédit",
    )
    borrower.credit_used = Decimal(borrower.credit_used or 0) + Decimal(loan.principal)

    tx = Transactions(
        tx_id=uuid.uuid4(),
        amount=loan.principal,
        currency_code=loan.currency_code,
        channel="internal",
        status="succeeded",
        initiated_by=borrower.user_id,
        receiver_wallet=wallet.wallet_id,
        description=f"Déblocage crédit {loan.loan_id}",
    )
    db.add(tx)

    loan.status = "active"
    loan.updated_at = datetime.utcnow()

    await db.commit()

    return LoanDisbursementResponse(
        loan_id=str(loan.loan_id),
        status=loan.status,
        credited_amount=Decimal(loan.principal),
        wallet_id=str(wallet.wallet_id),
    )


@router.get("/", response_model=LoanAdminList)
async def list_loans(
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    limit = min(limit, 200)
    offset = max(offset, 0)
    stmt = (
        select(Loans)
        .options(selectinload(Loans.loan_repayments), selectinload(Loans.users))
        .order_by(Loans.created_at.desc())
    )

    if status:
        stmt = stmt.where(Loans.status == status)

    rows = (await db.execute(stmt)).scalars().all()
    filtered: list[tuple[Loans, bool]] = []
    for loan in rows:
        overdue = has_overdue_installments(loan.loan_repayments or [])
        if overdue_only and not overdue:
            continue
        filtered.append((loan, overdue))

    total = len(filtered)
    page = filtered[offset : offset + limit]

    response: list[LoanAdminItem] = []
    for loan, overdue in page:
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
                product_type=loan.product_type,
                product_id=str(loan.product_id) if loan.product_id else None,
                business_name=loan.business_name,
            )
        )
    return LoanAdminList(total=total, items=response)


@router.post("/{loan_id}/repay")
async def repay_loan(
    loan_id: uuid.UUID,
    payload: LoanRepaymentPayload,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    loan = await db.get(Loans, loan_id)
    if not loan or loan.borrower_user != current_user.user_id:
        raise HTTPException(404, "Crédit introuvable.")
    if loan.status not in {"active", "in_arrears"}:
        raise HTTPException(400, "Ce crédit n'est pas éligible au remboursement.")

    installments = (
        await db.execute(
            select(LoanRepayments).where(LoanRepayments.loan_id == loan.loan_id).order_by(
                LoanRepayments.due_date
            )
        )
    ).scalars().all()
    if not installments:
        raise HTTPException(400, "Plan de remboursement introuvable.")

    outstanding = outstanding_balance(installments)
    amount = Decimal(payload.amount)
    if amount > outstanding:
        raise HTTPException(400, "Le montant dépasse le solde dû.")

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet or Decimal(wallet.available or 0) < amount:
        raise HTTPException(400, "Solde insuffisant.")

    remaining = amount
    for installment in installments:
        if remaining <= 0:
            break
        due_left = Decimal(installment.due_amount or 0) - Decimal(installment.paid_amount or 0)
        if due_left <= 0:
            continue
        pay = min(due_left, remaining)
        installment.paid_amount = Decimal(installment.paid_amount or 0) + pay
        installment.paid_at = datetime.utcnow()
        remaining -= pay

    if remaining > 0:
        raise HTTPException(400, "Impossible d'allouer entièrement le montant.")

    wallet.available = Decimal(wallet.available or 0) - amount
    await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="loan_repayment",
        reference=str(loan.loan_id),
        description="Remboursement du crédit",
    )
    current_user.credit_used = max(Decimal("0"), Decimal(current_user.credit_used or 0) - amount)

    tx = Transactions(
        tx_id=uuid.uuid4(),
        amount=amount,
        currency_code=loan.currency_code,
        channel="internal",
        status="succeeded",
        initiated_by=current_user.user_id,
        sender_wallet=wallet.wallet_id,
        description=f"Remboursement crédit {loan.loan_id}",
    )
    db.add(tx)

    loan.updated_at = datetime.utcnow()
    remaining_balance = outstanding_balance(installments)
    if remaining_balance <= 0:
        loan.status = "repaid"
    elif has_overdue_installments(installments):
        loan.status = "in_arrears"
    else:
        loan.status = "active"

    await db.commit()

    return {
        "loan_id": str(loan.loan_id),
        "status": loan.status,
        "remaining_balance": str(remaining_balance),
    }


@router.post("/{loan_id}/remind", response_model=LoanReminderResponse)
async def remind_loan_borrower(
    loan_id: uuid.UUID,
    payload: LoanReminderPayload,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    loan = await db.get(
        Loans,
        loan_id,
        options=[selectinload(Loans.loan_repayments), selectinload(Loans.users)],
    )
    if not loan:
        raise HTTPException(404, "Crédit introuvable.")
    borrower = loan.users
    if not borrower:
        raise HTTPException(404, "Emprunteur introuvable.")

    repayments = loan.loan_repayments or []
    overdue_installments = [
        inst
        for inst in repayments
        if inst.due_date
        and inst.due_date < date.today()
        and Decimal(inst.paid_amount or 0) < Decimal(inst.due_amount or 0)
    ]
    next_installment = next_due_installment(repayments)

    auto_message = (
        f"Rappel échéance: merci de régler votre crédit {loan.loan_id} "
        f"avant le {next_installment.due_date.isoformat()}"
        if next_installment and next_installment.due_date
        else "Merci de régulariser votre crédit PayLink."
    )
    message = payload.message or auto_message

    db.add(
        Notifications(
            user_id=borrower.user_id,
            channel="loan_reminder",
            subject="Rappel remboursement PayLink",
            message=message,
            metadata_={
                "loan_id": str(loan.loan_id),
                "reminder_by": str(admin.user_id),
                "overdue_installments": len(overdue_installments),
            },
        )
    )
    await db.commit()

    return LoanReminderResponse(
        loan_id=str(loan.loan_id),
        reminder_sent=True,
        overdue_installments=len(overdue_installments),
        message=message,
    )
