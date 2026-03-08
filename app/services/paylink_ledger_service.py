from decimal import Decimal
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PaylinkLedgerService:
    @staticmethod
    def _normalize_postings(postings: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for index, raw in enumerate(postings or []):
            direction = str(raw.get("direction") or "").upper()
            if direction not in {"DEBIT", "CREDIT"}:
                raise ValueError(f"Invalid posting direction at index={index}: {raw.get('direction')}")

            amount = Decimal(str(raw.get("amount") or "0"))
            if amount < 0:
                raise ValueError(f"Posting amount cannot be negative at index={index}")
            if amount == 0:
                continue

            normalized.append(
                {
                    "account_code": raw.get("account_code"),
                    "direction": direction,
                    "amount": amount,
                    "currency": raw.get("currency"),
                }
            )

        if not normalized:
            raise ValueError("No positive postings to journalize")
        return normalized

    @staticmethod
    def _assert_balanced_by_currency(postings: list[dict]) -> None:
        buckets: dict[str, dict[str, Decimal]] = {}
        for posting in postings:
            ccy = str(posting.get("currency") or "").upper()
            if not ccy:
                # Currency can be inferred from account. Validation is done after account lookup.
                continue
            current = buckets.setdefault(ccy, {"DEBIT": Decimal("0"), "CREDIT": Decimal("0")})
            current[posting["direction"]] += posting["amount"]

        for ccy, sums in buckets.items():
            if sums["DEBIT"] != sums["CREDIT"]:
                raise ValueError(
                    f"Unbalanced postings for currency={ccy}: debit={sums['DEBIT']} credit={sums['CREDIT']}"
                )

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
        try:
            normalized_postings = PaylinkLedgerService._normalize_postings(postings)

            # 1) Idempotency: reuse journal if exists
            res = await db.execute(
                text("SELECT journal_id FROM paylink.ledger_journal WHERE tx_id=:tx_id LIMIT 1"),
                {"tx_id": tx_id},
            )
            journal_id = res.scalar_one_or_none()
            if journal_id:
                existing_count = await db.execute(
                    text("SELECT COUNT(*) FROM paylink.ledger_entries WHERE journal_id=:jid"),
                    {"jid": journal_id},
                )
                if int(existing_count.scalar_one() or 0) > 0:
                    return journal_id

            prepared: list[dict] = []
            # 2) Resolve account + currency
            for p in normalized_postings:
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
                prepared.append(
                    {
                        "account_id": account_id,
                        "direction": p["direction"],
                        "amount": p["amount"],
                        "currency_code": effective_currency,
                    }
                )

            # Hard-fail before any write if not balanced.
            PaylinkLedgerService._assert_balanced_by_currency(prepared)

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

            # 3) Entries
            for entry in prepared:
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
                        "aid": entry["account_id"],
                        "dir": entry["direction"],
                        "amt": entry["amount"],
                        "ccy": entry["currency_code"],
                    },
                )

            await db.commit()
            return journal_id
        except Exception:
            await db.rollback()
            raise
