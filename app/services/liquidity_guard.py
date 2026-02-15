from decimal import Decimal

from app.config import settings
from app.services.ledger_service import LedgerService
from app.services.paylink_ledger_service import PaylinkLedgerService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class LiquidityGuard:
    @staticmethod
    async def assert_balance(
        db: AsyncSession,
        account_code: str,
        token: str,
        required_amount: Decimal,
    ):
        balance = await PaylinkLedgerService.get_balance(
            db,
            account_code=account_code,
            currency=token,
        )

        if balance < required_amount:
            raise ValueError(
                f"Insufficient liquidity in {account_code}: {balance} < {required_amount}"
            )

    @staticmethod
    async def assert_treasury_can_fill(
        db: AsyncSession,
        token: str,
        token_amount: Decimal,
        bif_amount: Decimal,
    ):
        if not settings.SYSTEM_TREASURY_USER_ID:
            raise ValueError("SYSTEM_TREASURY_USER_ID not set")

        # Treasury token balance (e.g. TREASURY_USDC / TREASURY_USDT)
        acct_token = f"TREASURY_{token}"
        bal_token = await LedgerService.get_balance(db, account_code=acct_token, token=token)
        if bal_token < token_amount:
            raise ValueError(f"Insufficient treasury {token}: {bal_token} < {token_amount}")

        # Treasury BIF balance
        bal_bif = await LedgerService.get_balance(db, account_code="TREASURY_BIF", token="BIF")
        if bal_bif < bif_amount:
            raise ValueError(f"Insufficient treasury BIF: {bal_bif} < {bif_amount}")

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
