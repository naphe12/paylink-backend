from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class LiquidityGuard:
    @staticmethod
    async def require_treasury(
        db: AsyncSession,
        *,
        currency: str,
        required_amount: float,
        buffer_ratio: float = 0.02,
    ) -> tuple[bool, float, float]:
        account_code = f"TREASURY_{currency}"

        res = await db.execute(
            text(
                """
                SELECT balance
                FROM paylink.v_ledger_balances
                WHERE code = :code
                  AND currency_code = :cc
                """
            ),
            {
                "code": account_code,
                "cc": currency,
            },
        )

        row = res.first()
        balance = float(row[0]) if row else 0.0
        needed = float(required_amount) * (1.0 + float(buffer_ratio))

        return balance >= needed, balance, needed

    @staticmethod
    async def check(
        db: AsyncSession,
        *,
        account_code: str,
        currency_code: str,
        required_amount: float,
        buffer_ratio: float = 0.02,  # garde 2%
    ) -> tuple[bool, float, float]:
        res = await db.execute(text("""
          SELECT balance
          FROM paylink.v_ledger_balances
          WHERE code = :code AND currency_code = :cc
        """), {"code": account_code, "cc": currency_code})
        row = res.first()
        balance = float(row[0]) if row else 0.0

        needed = float(required_amount) * (1.0 + float(buffer_ratio))
        return (balance >= needed, balance, needed)

    @staticmethod
    async def require_available(
        db: AsyncSession,
        *,
        treasury_account_code: str,
        currency_code: str,
        required_amount: float,
        buffer: float = 0.0,
    ) -> tuple[bool, float, float]:
        return await LiquidityGuard.check(
            db,
            account_code=treasury_account_code,
            currency_code=currency_code,
            required_amount=required_amount,
            buffer_ratio=buffer,
        )
