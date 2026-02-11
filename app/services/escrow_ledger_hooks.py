from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escrow_order import EscrowOrder
from services.paylink_ledger_service import PaylinkLedgerService


async def post_funded_usdc_deposit_journal(
    db: AsyncSession,
    order: EscrowOrder,
) -> None:
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=order.id,
        description="Escrow USDC deposit funded",
        postings=[
            {
                "account_code": "CUSTODY_USDC",
                "direction": "DEBIT",
                "amount": order.usdc_received,
                "currency": "USDC",
            },
            {
                "account_code": "ESCROW_USDC_LIABILITY",
                "direction": "CREDIT",
                "amount": order.usdc_received,
                "currency": "USDC",
            },
        ],
    )


async def post_swap_usdc_to_usdt_journal(
    db: AsyncSession,
    order: EscrowOrder,
) -> None:
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=order.id,
        description="Escrow swap USDC to USDT",
        postings=[
            {
                "account_code": "ESCROW_USDC_LIABILITY",
                "direction": "DEBIT",
                "amount": order.usdc_received,
                "currency": "USDC",
            },
            {
                "account_code": "CUSTODY_USDC",
                "direction": "CREDIT",
                "amount": order.usdc_received,
                "currency": "USDC",
            },
            {
                "account_code": "TREASURY_USDT",
                "direction": "DEBIT",
                "amount": order.usdt_received,
                "currency": "USDT",
            },
            {
                "account_code": "ESCROW_USDT_LIABILITY",
                "direction": "CREDIT",
                "amount": order.usdt_received,
                "currency": "USDT",
            },
            {
                "account_code": "ESCROW_USDT_LIABILITY",
                "direction": "DEBIT",
                "amount": order.conversion_fee_usdt,
                "currency": "USDT",
            },
            {
                "account_code": "REVENUE_FEES_USDT",
                "direction": "CREDIT",
                "amount": order.conversion_fee_usdt,
                "currency": "USDT",
            },
        ],
    )


async def post_payout_bif_journal(
    db: AsyncSession,
    order: EscrowOrder,
) -> None:
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=order.id,
        description="Escrow payout BIF",
        postings=[
            {
                "account_code": "ESCROW_BIF_LIABILITY",
                "direction": "DEBIT",
                "amount": order.bif_target,
                "currency": "BIF",
            },
            {
                "account_code": "CASH_BIF",
                "direction": "CREDIT",
                "amount": order.bif_target,
                "currency": "BIF",
            },
        ],
    )


from services.paylink_ledger_service import PaylinkLedgerService

async def on_payout_confirmed(db, order):
    """
    Ledger hook for final BIF payout.
    """
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=order.id,
        description="Escrow BIF payout confirmed",
        postings=[
            {
                "account_code": "ESCROW_BIF_LIABILITY",
                "direction": "DEBIT",
                "amount": order.bif_paid or order.bif_target,
                "currency": "BIF",          # ✅ BIF est ISO-4217
            },
            {
                "account_code": "CASH_BIF",
                "direction": "CREDIT",
                "amount": order.bif_paid or order.bif_target,
                "currency": "BIF",
            },
        ],
        metadata={
            "escrow_order_id": str(order.id),
            "event": "PAYOUT",
        },
    )
