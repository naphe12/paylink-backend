from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_balance_events import ClientBalanceEvents
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets

Direction = Literal["credit", "debit"]


def _to_decimal(value: Decimal | float | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def log_wallet_movement(
    db: AsyncSession,
    *,
    wallet: Wallets,
    user_id: UUID | None = None,
    amount: Decimal | float | int,
    direction: Direction,
    operation_type: str,    
    reference: str | None = None,
    description: str | None = None,
):
    """
    Enregistre une ligne dans l'historique du wallet après une opération.
    """
    if wallet is None:
        return None

    dec_amount = _to_decimal(amount).copy_abs()
    if dec_amount == 0:
        return None

    entry = WalletTransactions(
        wallet_id=wallet.wallet_id,
        user_id=user_id or wallet.user_id,
        amount=dec_amount,
        direction=direction,
        operation_type=operation_type,
        currency_code=wallet.currency_code,
        balance_after=wallet.available,
        reference=reference,
        description=description,
    )
    db.add(entry)
    await db.flush()

    event_user_id = user_id or wallet.user_id
    if event_user_id:
        signed_delta = dec_amount if direction == "credit" else -dec_amount
        balance_after = _to_decimal(wallet.available or 0)
        balance_before = balance_after - signed_delta
        db.add(
            ClientBalanceEvents(
                user_id=event_user_id,
                balance_before=balance_before,
                balance_after=balance_after,
                amount_delta=signed_delta,
                source=operation_type or "wallet_transaction",
                occurred_at=datetime.now(timezone.utc),
                currency=wallet.currency_code,
            )
        )
        await db.flush()
    return entry
