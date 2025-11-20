# app/services/loan_workflow.py
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Tuple

from app.models.loanrepayments import LoanRepayments
from app.models.users import Users


def map_score_to_risk(score: int | None) -> str:
    """Return a textual risk bucket based on the stored risk score."""
    score = score or 0
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def user_credit_capacity(user: Users) -> Tuple[Decimal, Decimal]:
    """Return (limit, available) credit capacity."""
    limit = Decimal(user.credit_limit or 0)
    used = Decimal(user.credit_used or 0)
    return limit, max(Decimal("0"), limit - used)


def ensure_month_increment(start: date, months: int) -> date:
    """Pure-Python month arithmetic to avoid external deps."""
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_repayment_schedule(
    principal: Decimal,
    apr_percent: Decimal,
    term_months: int,
    start_date: date | None = None,
) -> List[Tuple[date, Decimal]]:
    """
    Generates a flat repayment schedule (monthly installments with simple interest).
    """
    if term_months <= 0:
        raise ValueError("term_months must be positive")

    monthly_rate = (apr_percent / Decimal("100")) / Decimal("12")
    total_interest = principal * monthly_rate * Decimal(term_months)
    total_to_repay = principal + total_interest
    base_installment = (total_to_repay / Decimal(term_months)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )

    schedule: List[Tuple[date, Decimal]] = []
    start = start_date or date.today()
    remaining = total_to_repay

    for idx in range(term_months):
        due_date = ensure_month_increment(start, idx + 1)
        amount = base_installment if idx < term_months - 1 else remaining
        amount = amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        schedule.append((due_date, amount))
        remaining -= amount

    return schedule


def outstanding_balance(repayments: Iterable[LoanRepayments]) -> Decimal:
    """Compute the remaining balance for a list of installments."""
    remaining = Decimal("0")
    for installment in repayments:
        due = Decimal(installment.due_amount or 0)
        paid = Decimal(installment.paid_amount or 0)
        remaining += max(Decimal("0"), due - paid)
    return remaining


def has_overdue_installments(repayments: Iterable[LoanRepayments]) -> bool:
    today = date.today()
    for installment in repayments:
        if (
            installment.due_date
            and installment.due_date < today
            and Decimal(installment.paid_amount or 0) < Decimal(installment.due_amount or 0)
        ):
            return True
    return False


def summarize_installments(repayments: Iterable[LoanRepayments]):
    """Return installments sorted by due date for serialization."""
    return sorted(repayments, key=lambda inst: inst.due_date or date.today())


def next_due_installment(repayments: Iterable[LoanRepayments]) -> LoanRepayments | None:
    future_installments = [
        inst
        for inst in repayments
        if Decimal(inst.paid_amount or 0) < Decimal(inst.due_amount or 0)
    ]
    if not future_installments:
        return None
    return min(future_installments, key=lambda inst: inst.due_date or date.today())


def installments_progress(repayments: Iterable[LoanRepayments]) -> Tuple[int, int]:
    """
    Returns (paid_count, total_count) based on whether installments are fully paid.
    """
    paid = 0
    total = 0
    for installment in repayments:
        total += 1
        due = Decimal(installment.due_amount or 0)
        paid_amount = Decimal(installment.paid_amount or 0)
        if paid_amount >= due and due > 0:
            paid += 1
    return paid, total
