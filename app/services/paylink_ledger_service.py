from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID


class PaylinkLedgerService:
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
            res = await db.execute(
                text(
                    """
                    INSERT INTO paylink.ledger_journal (tx_id, description, metadata)
                    VALUES (:tx_id, :desc, :meta)
                    RETURNING journal_id
                """
                ),
                {"tx_id": tx_id, "desc": description, "meta": metadata or {}},
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
