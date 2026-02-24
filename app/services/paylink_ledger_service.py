from decimal import Decimal
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PaylinkLedgerService:
    @staticmethod
    async def get_balance(
        db: AsyncSession,
        *,
        account_code: str,
        currency: str,
    ) -> Decimal:
        res = await db.execute(
            text(
                """
                SELECT balance
                FROM paylink.v_ledger_balances
                WHERE code = :code
                  AND currency_code = :ccy
                LIMIT 1
                """
            ),
            {"code": account_code, "ccy": currency},
        )
        row = res.first()
        if not row or row[0] is None:
            return Decimal("0")
        return Decimal(str(row[0]))

    @staticmethod
    async def post_journal(
        db: AsyncSession,
        *,
        tx_id: UUID,  # escrow_order.id
        description: str,
        postings: list[dict],  # {account_code, direction, amount, currency?}
        metadata: dict | None = None,
    ) -> UUID:
        # 1) Idempotency: reuse journal if exists
        res = await db.execute(
            text("SELECT journal_id FROM paylink.ledger_journal WHERE tx_id=:tx_id LIMIT 1"),
            {"tx_id": tx_id},
        )
        journal_id = res.scalar_one_or_none()

        if not journal_id:
            # Ensure metadata is JSON-serializable for raw SQL + asyncpg.
            meta_payload = json.dumps(metadata or {})
            res = await db.execute(
                text(
                    """
                    INSERT INTO paylink.ledger_journal (tx_id, description, metadata)
                    VALUES (:tx_id, :desc, CAST(:meta AS jsonb))
                    RETURNING journal_id
                """
                ),
                {"tx_id": tx_id, "desc": description, "meta": meta_payload},
            )
            journal_id = res.scalar_one()

        # 2) Entries
        for p in postings:
            # Some business flows can produce zero-fee lines; skip non-positive entries
            # to satisfy DB check constraints on ledger amount.
            amount = Decimal(str(p["amount"]))
            if amount <= 0:
                continue

            acc = await db.execute(
                text(
                    """
                    SELECT account_id, currency_code
                    FROM paylink.ledger_accounts
                    WHERE code = :c
                    LIMIT 1
                    """
                ),
                {"c": p["account_code"]},
            )
            acc_row = acc.first()
            if not acc_row:
                raise ValueError(f"Ledger account not found: {p['account_code']}")
            account_id = acc_row[0]
            account_currency = str(acc_row[1]) if acc_row[1] else None
            effective_currency = str(p.get("currency") or account_currency or "USD").upper()

            await db.execute(
                text(
                    """
                    INSERT INTO paylink.ledger_entries
                      (journal_id, account_id, direction, amount, currency_code)
                    VALUES
                      (:jid, :aid, :dir, :amt, :ccy)
                """
                ),
                {
                    "jid": journal_id,
                    "aid": account_id,
                    "dir": p["direction"],  # 'DEBIT' | 'CREDIT'
                    "amt": amount,
                    "ccy": effective_currency,
                },
            )

        await db.commit()
        return journal_id
