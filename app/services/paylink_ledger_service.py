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
        postings: list[dict],  # {account_code, direction, amount, currency='USD'}
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
            acc = await db.execute(
                text("SELECT account_id FROM paylink.ledger_accounts WHERE code=:c"),
                {"c": p["account_code"]},
            )
            account_id = acc.scalar_one()

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
                    "amt": p["amount"],
                    "ccy": p.get("currency", "USD"),
                },
            )

        await db.commit()
        return journal_id
