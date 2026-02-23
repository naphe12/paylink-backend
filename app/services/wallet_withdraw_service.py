from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wallet_service import debit_user_usdc

USDC_CURRENCY = "USDC"
WITHDRAWAL_PENDING_ACCOUNT = "WITHDRAWAL_PENDING_USDC"


async def _ensure_withdrawals_table(db: AsyncSession) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS paylink"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.wallet_withdrawals (
                id uuid PRIMARY KEY,
                user_id uuid NOT NULL,
                currency_code char(3) NOT NULL,
                amount numeric(20, 6) NOT NULL CHECK (amount > 0),
                to_address text NOT NULL,
                status text NOT NULL,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


async def request_usdc_withdrawal(
    db: AsyncSession,
    *,
    user_id: str,
    amount: Decimal,
    to_address: str,
    ref: str | None = None,
) -> str:
    normalized_amount = Decimal(str(amount))
    if normalized_amount <= 0:
        raise ValueError("Amount must be > 0")

    destination = str(to_address or "").strip()
    if len(destination) < 8:
        raise ValueError("Invalid destination address")

    effective_ref = ref or f"USDC_WITHDRAW:{user_id}:{normalized_amount.normalize()}:{destination}"
    withdrawal_id = str(uuid4())

    await _ensure_withdrawals_table(db)
    existing = await db.execute(
        text(
            """
            SELECT id
            FROM paylink.wallet_withdrawals
            WHERE metadata ->> 'ref' = :ref
            LIMIT 1
            """
        ),
        {"ref": effective_ref},
    )
    row = existing.first()
    if row:
        return str(row[0])

    await debit_user_usdc(
        user_id=user_id,
        amount=normalized_amount,
        destination_account_code=WITHDRAWAL_PENDING_ACCOUNT,
        ref=effective_ref,
        description="External USDC withdrawal requested",
        db=db,
    )

    await db.execute(
        text(
            """
            INSERT INTO paylink.wallet_withdrawals
                (id, user_id, currency_code, amount, to_address, status, metadata)
            VALUES
                (CAST(:id AS uuid), CAST(:user_id AS uuid), :currency, :amount, :to_address, 'PENDING', CAST(:metadata AS jsonb))
            """
        ),
        {
            "id": withdrawal_id,
            "user_id": str(user_id),
            "currency": USDC_CURRENCY,
            "amount": normalized_amount,
            "to_address": destination,
            "metadata": json.dumps({"ref": effective_ref}),
        },
    )

    return withdrawal_id
