from __future__ import annotations

import decimal
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_budget_rules import FinancialBudgetRules
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
from app.routers.wallet.wallet import financial_summary


def _categorize_operation(operation_type: str | None) -> str:
    op = str(operation_type or "").lower()
    if "savings" in op or "epargne" in op:
        return "epargne"
    if "transfer" in op:
        return "transferts"
    if "payment" in op or "invoice" in op:
        return "paiements"
    if "cash" in op or "deposit" in op or "withdraw" in op:
        return "cash"
    if "loan" in op or "credit" in op:
        return "credit"
    if "topup" in op:
        return "recharges"
    return "autres"


async def get_financial_insights(db: AsyncSession, *, current_user: Users) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    trailing_start = month_start - timedelta(days=90)

    rows = (
        await db.execute(
            select(
                WalletTransactions.direction,
                WalletTransactions.amount,
                WalletTransactions.currency_code,
                WalletTransactions.operation_type,
                WalletTransactions.created_at,
            )
            .where(
                WalletTransactions.user_id == current_user.user_id,
                WalletTransactions.created_at >= trailing_start,
            )
            .order_by(WalletTransactions.created_at.desc())
        )
    ).all()

    summary = await financial_summary(db=db, current_user=current_user)
    currency_code = str(summary.wallet_currency or "EUR").upper()

    month_inflows = decimal.Decimal("0")
    month_outflows = decimal.Decimal("0")
    trailing_monthly_outflows: dict[str, decimal.Decimal] = {}
    category_totals: dict[str, decimal.Decimal] = {}
    budget_rule_rows = (
        await db.execute(
            select(FinancialBudgetRules).where(FinancialBudgetRules.user_id == current_user.user_id)
        )
    ).scalars().all()
    budget_rule_map = {
        str(rule.category or "").lower(): decimal.Decimal(str(rule.limit_amount or 0))
        for rule in budget_rule_rows
        if str(rule.currency_code or "").upper() == currency_code
    }

    for direction, amount, tx_currency, operation_type, created_at in rows:
        normalized_currency = str(tx_currency or "").upper()
        if normalized_currency != currency_code:
            continue
        raw_amount = decimal.Decimal(str(amount or 0))
        normalized_direction = str(direction or "").lower()
        is_outflow = normalized_direction.startswith("debit") or normalized_direction == "out"
        month_key = created_at.strftime("%Y-%m") if created_at else None
        if month_key and is_outflow:
            trailing_monthly_outflows[month_key] = trailing_monthly_outflows.get(month_key, decimal.Decimal("0")) + raw_amount
        if created_at and created_at >= month_start:
            if is_outflow:
                month_outflows += raw_amount
                category = _categorize_operation(operation_type)
                category_totals[category] = category_totals.get(category, decimal.Decimal("0")) + raw_amount
            else:
                month_inflows += raw_amount

    non_zero_months = [value for value in trailing_monthly_outflows.values() if value > 0]
    if non_zero_months:
        suggested_budget = (sum(non_zero_months, decimal.Decimal("0")) / decimal.Decimal(len(non_zero_months))).quantize(
            decimal.Decimal("0.01")
        )
    else:
        suggested_budget = month_outflows.quantize(decimal.Decimal("0.01"))

    active_budget = budget_rule_map.get("global", suggested_budget).quantize(decimal.Decimal("0.01"))
    budget_source = "custom" if "global" in budget_rule_map else "suggested"
    remaining_to_spend = max(active_budget - month_outflows, decimal.Decimal("0")).quantize(decimal.Decimal("0.01"))
    current_savings = decimal.Decimal("0")
    for direction, amount, tx_currency, operation_type, _ in rows:
        if str(tx_currency or "").upper() != currency_code:
            continue
        if _categorize_operation(operation_type) != "epargne":
            continue
        raw_amount = decimal.Decimal(str(amount or 0))
        normalized_direction = str(direction or "").lower()
        if normalized_direction.startswith("debit") or normalized_direction == "out":
            current_savings += raw_amount
        else:
            current_savings -= raw_amount
    current_savings = max(current_savings, decimal.Decimal("0")).quantize(decimal.Decimal("0.01"))

    total_category_spend = sum(category_totals.values(), decimal.Decimal("0"))
    top_spending_categories = []
    for category, amount in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)[:4]:
        budget_limit = budget_rule_map.get(category)
        remaining_budget = None
        is_over_limit = False
        if budget_limit is not None:
            remaining_budget = max(budget_limit - amount, decimal.Decimal("0")).quantize(decimal.Decimal("0.01"))
            is_over_limit = amount > budget_limit
        top_spending_categories.append(
            {
                "category": category,
                "amount": amount.quantize(decimal.Decimal("0.01")),
                "share_percent": float(round((amount / total_category_spend) * decimal.Decimal("100"), 2)) if total_category_spend > 0 else 0,
                "budget_limit": budget_limit.quantize(decimal.Decimal("0.01")) if budget_limit is not None else None,
                "remaining_budget": remaining_budget,
                "is_over_limit": is_over_limit,
            }
        )

    budget_rules = []
    for category, limit_amount in sorted(budget_rule_map.items()):
        if category == "global":
            continue
        spent_amount = category_totals.get(category, decimal.Decimal("0")).quantize(decimal.Decimal("0.01"))
        remaining_amount = max(limit_amount - spent_amount, decimal.Decimal("0")).quantize(decimal.Decimal("0.01"))
        progress_percent = float(round((spent_amount / limit_amount) * decimal.Decimal("100"), 2)) if limit_amount > 0 else 0
        budget_rules.append(
            {
                "category": category,
                "limit_amount": limit_amount.quantize(decimal.Decimal("0.01")),
                "spent_amount": spent_amount,
                "remaining_amount": remaining_amount,
                "progress_percent": progress_percent,
                "is_over_limit": spent_amount > limit_amount,
            }
        )

    budget_usage_percent = (
        float(round((month_outflows / active_budget) * decimal.Decimal("100"), 2))
        if active_budget > 0
        else 0
    )
    over_limit_count = sum(1 for item in budget_rules if item["is_over_limit"])

    if active_budget > 0 and month_outflows > active_budget:
        alert_level = "critical"
        alert_message = "Le budget mensuel est depasse."
    elif over_limit_count > 0:
        alert_level = "critical"
        alert_message = "Au moins une categorie depasse son plafond."
    elif budget_usage_percent >= 80:
        alert_level = "watch"
        alert_message = "Le budget du mois approche de sa limite."
    else:
        alert_level = "healthy"
        alert_message = "Le budget reste sous controle."

    guidance: list[str] = []
    if month_outflows > active_budget and active_budget > 0:
        guidance.append("Vos depenses du mois depassent votre budget actif.")
    if remaining_to_spend <= decimal.Decimal("0"):
        guidance.append("Le budget actif de ce mois est deja consomme.")
    if current_savings <= decimal.Decimal("0"):
        guidance.append("Aucune epargne nette detectee sur la periode recente.")
    if any(item["is_over_limit"] for item in budget_rules):
        guidance.append("Au moins une categorie de depense depasse sa limite definie.")
    if not guidance:
        guidance.append("Votre rythme de depense reste coherent avec votre historique recent.")

    return {
        "currency_code": currency_code,
        "month_inflows": month_inflows.quantize(decimal.Decimal("0.01")),
        "month_outflows": month_outflows.quantize(decimal.Decimal("0.01")),
        "month_net": (month_inflows - month_outflows).quantize(decimal.Decimal("0.01")),
        "suggested_budget": suggested_budget,
        "active_budget": active_budget,
        "budget_source": budget_source,
        "remaining_to_spend": remaining_to_spend,
        "current_savings": current_savings,
        "budget_usage_percent": budget_usage_percent,
        "over_limit_count": over_limit_count,
        "alert_level": alert_level,
        "alert_message": alert_message,
        "top_spending_categories": top_spending_categories,
        "budget_rules": budget_rules,
        "guidance": guidance,
    }


async def upsert_financial_budget_rule(db: AsyncSession, *, current_user: Users, payload) -> dict:
    summary = await financial_summary(db=db, current_user=current_user)
    currency_code = str(summary.wallet_currency or "EUR").upper()
    category = str(payload.category or "").strip().lower()
    if not category:
        raise HTTPException(status_code=400, detail="Categorie budgetaire obligatoire")

    item = await db.scalar(
        select(FinancialBudgetRules).where(
            FinancialBudgetRules.user_id == current_user.user_id,
            FinancialBudgetRules.category == category,
        )
    )
    now = datetime.now(timezone.utc)
    if item:
        item.limit_amount = payload.limit_amount
        item.currency_code = currency_code
        item.updated_at = now
    else:
        item = FinancialBudgetRules(
            user_id=current_user.user_id,
            category=category,
            limit_amount=payload.limit_amount,
            currency_code=currency_code,
            updated_at=now,
        )
        db.add(item)
    await db.commit()
    return await get_financial_insights(db, current_user=current_user)


async def delete_financial_budget_rule(
    db: AsyncSession,
    *,
    current_user: Users,
    category: str,
) -> dict:
    normalized_category = str(category or "").strip().lower()
    if not normalized_category:
        raise HTTPException(status_code=400, detail="Categorie budgetaire obligatoire")

    item = await db.scalar(
        select(FinancialBudgetRules).where(
            FinancialBudgetRules.user_id == current_user.user_id,
            FinancialBudgetRules.category == normalized_category,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Regle budgetaire introuvable")

    await db.delete(item)
    await db.commit()
    return await get_financial_insights(db, current_user=current_user)
