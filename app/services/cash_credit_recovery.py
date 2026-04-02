from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_line_events import CreditLineEvents
from app.models.credit_line_history import CreditLineHistory
from app.models.credit_lines import CreditLines
from app.models.users import Users
from app.models.wallets import Wallets


async def apply_cash_deposit_with_credit_recovery(
    db: AsyncSession,
    *,
    user: Users,
    wallet: Wallets,
    amount: Decimal,
    credit_event_source: str,
    credit_history_description: str,
) -> dict[str, Decimal | bool | None]:
    deposit_amount = Decimal(amount or 0)
    wallet_before = Decimal(wallet.available or 0)
    wallet_after = wallet_before + deposit_amount
    wallet.available = wallet_after

    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )

    credit_recovered = Decimal("0")
    credit_available_before = None
    credit_available_after = None

    if credit_line:
        used_before = Decimal(credit_line.used_amount or 0)
        credit_available_before = max(Decimal(credit_line.outstanding_amount or 0), Decimal("0"))
        credit_recovered = min(deposit_amount, used_before)
        if credit_recovered > 0:
            credit_line.used_amount = max(Decimal("0"), used_before - credit_recovered)
            credit_line.outstanding_amount = credit_available_before + credit_recovered
            credit_line.updated_at = datetime.utcnow()
            credit_available_after = Decimal(credit_line.outstanding_amount or 0)

            user.credit_limit = Decimal(credit_line.initial_amount or 0)
            user.credit_used = Decimal(credit_line.used_amount or 0)

            db.add(
                CreditLineEvents(
                    credit_line_id=credit_line.credit_line_id,
                    user_id=user.user_id,
                    amount_delta=-credit_recovered,
                    currency_code=credit_line.currency_code,
                    old_limit=credit_available_before,
                    new_limit=credit_available_after,
                    operation_code=9002,
                    status="completed",
                    source=credit_event_source,
                    occurred_at=datetime.utcnow(),
                )
            )
            db.add(
                CreditLineHistory(
                    user_id=user.user_id,
                    transaction_id=None,
                    amount=-credit_recovered,
                    credit_available_before=credit_available_before,
                    credit_available_after=credit_available_after,
                    description=credit_history_description,
                )
            )
        else:
            credit_available_after = credit_available_before

    return {
        "wallet_before": wallet_before,
        "wallet_after": wallet_after,
        "credit_recovered": credit_recovered,
        "credit_available_before": credit_available_before,
        "credit_available_after": credit_available_after,
        "has_credit_line": bool(credit_line),
        "credit_line_id": getattr(credit_line, "credit_line_id", None),
    }


async def apply_cash_withdraw_with_credit_usage(
    db: AsyncSession,
    *,
    user: Users,
    wallet: Wallets,
    amount: Decimal,
    credit_event_source: str,
    credit_history_description: str,
) -> dict[str, Decimal | bool | None]:
    withdraw_amount = Decimal(amount or 0)
    wallet_before = Decimal(wallet.available or 0)

    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )

    credit_consumed = Decimal("0")
    credit_available_before = None
    credit_available_after = None

    if credit_line:
        credit_available_before = max(Decimal(credit_line.outstanding_amount or 0), Decimal("0"))
        if wallet_before + credit_available_before < withdraw_amount:
            raise ValueError("Capacite insuffisante pour effectuer ce retrait.")
        credit_consumed = min(withdraw_amount, credit_available_before)
        if credit_consumed > 0:
            used_before = Decimal(credit_line.used_amount or 0)
            credit_line.used_amount = used_before + credit_consumed
            credit_line.outstanding_amount = max(Decimal("0"), credit_available_before - credit_consumed)
            credit_line.updated_at = datetime.utcnow()
            credit_available_after = Decimal(credit_line.outstanding_amount or 0)

            user.credit_limit = Decimal(credit_line.initial_amount or 0)
            user.credit_used = Decimal(credit_line.used_amount or 0)

            db.add(
                CreditLineEvents(
                    credit_line_id=credit_line.credit_line_id,
                    user_id=user.user_id,
                    amount_delta=-credit_consumed,
                    currency_code=credit_line.currency_code,
                    old_limit=credit_available_before,
                    new_limit=credit_available_after,
                    operation_code=9101,
                    status="used",
                    source=credit_event_source,
                    occurred_at=datetime.utcnow(),
                )
            )
            db.add(
                CreditLineHistory(
                    user_id=user.user_id,
                    transaction_id=None,
                    amount=-credit_consumed,
                    credit_available_before=credit_available_before,
                    credit_available_after=credit_available_after,
                    description=credit_history_description,
                )
            )
        else:
            credit_available_after = credit_available_before
    elif wallet_before < withdraw_amount:
        raise ValueError("Solde insuffisant pour effectuer ce retrait.")

    wallet_after = wallet_before - withdraw_amount
    wallet.available = wallet_after

    return {
        "wallet_before": wallet_before,
        "wallet_after": wallet_after,
        "credit_consumed": credit_consumed,
        "credit_available_before": credit_available_before,
        "credit_available_after": credit_available_after,
        "has_credit_line": bool(credit_line),
        "credit_line_id": getattr(credit_line, "credit_line_id", None),
    }
