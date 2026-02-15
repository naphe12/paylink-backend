from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@dataclass
class Posting:
    account_code: str
    direction: str  # 'DEBIT'|'CREDIT'
    amount: Decimal

class LedgerService:
    @staticmethod
    async def get_balance(
        db: AsyncSession,
        *,
        account_code: str,
        token: str,
    ) -> Decimal:
        res = await db.execute(
            text(
                """
                SELECT balance
                FROM paylink.v_ledger_balances
                WHERE code = :code
                  AND currency_code = :cc
                LIMIT 1
                """
            ),
            {"code": account_code, "cc": token},
        )
        row = res.first()
        if not row or row[0] is None:
            return Decimal("0")
        return Decimal(str(row[0]))

    @staticmethod
    async def post_entry(db: AsyncSession, ref: str, description: str, postings: list[Posting]) -> str:
        """
        Idempotent: journal_entries.ref UNIQUE.
        Balanced: trigger asserts debit == credit at commit.
        """
        # 1) create entry if not exists
        entry = await db.execute(text("""
            INSERT INTO ledger.journal_entries (ref, description)
            VALUES (:ref, :desc)
            ON CONFLICT (ref) DO NOTHING
            RETURNING id
        """), {"ref": ref, "desc": description})
        row = entry.first()
        if row:
            entry_id = row[0]
        else:
            # entry already exists, return existing id (idempotent)
            ex = await db.execute(text("SELECT id FROM ledger.journal_entries WHERE ref=:ref"), {"ref": ref})
            entry_id = ex.scalar_one()

        # 2) insert postings
        for p in postings:
            acc = await db.execute(text("SELECT id FROM ledger.accounts WHERE code=:c"), {"c": p.account_code})
            acc_id = acc.scalar_one()

            await db.execute(text("""
                INSERT INTO ledger.postings (entry_id, account_id, direction, amount)
                VALUES (:eid, :aid, :dir, :amt)
            """), {"eid": entry_id, "aid": acc_id, "dir": p.direction, "amt": p.amount})

        await db.commit()
        return str(entry_id)
