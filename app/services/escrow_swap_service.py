from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.escrow_order import EscrowOrder
from models.escrow_swap import EscrowSwap
from models.escrow_event import EscrowEvent
from models.escrow_enums import EscrowOrderStatus

from services.swap_engine import SwapProvider


class EscrowSwapService:
    def __init__(self, provider: SwapProvider):
        self.provider = provider

    async def execute_swap(self, db: AsyncSession, order_id) -> EscrowSwap:
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order:
            raise ValueError("Order not found")

        if order.status != EscrowOrderStatus.FUNDED:
            raise ValueError(f"Order must be FUNDED to swap, current={order.status}")

        usdc_amount: Decimal = order.usdc_received
        if usdc_amount is None or usdc_amount <= 0:
            raise ValueError("usdc_received must be > 0")

        swap_res = await self.provider.swap_usdc_to_usdt(usdc_amount)

        # Persist swap row
        swap = EscrowSwap(
            order_id=order.id,
            mode=order.conversion_mode,
            input_amount=usdc_amount,
            output_amount=swap_res.output_amount_usdt,
            fee_amount=swap_res.fee_amount_usdt,
            rate=swap_res.rate,
            reference=swap_res.reference,
            executed_at=datetime.now(timezone.utc),
        )
        db.add(swap)

        # Update order aggregate
        order.usdt_received = swap_res.output_amount_usdt
        order.conversion_fee_usdt = swap_res.fee_amount_usdt
        order.conversion_rate_usdc_usdt = swap_res.rate
        order.swap_reference = swap_res.reference
        order.swapped_at = datetime.now(timezone.utc)
        order.status = EscrowOrderStatus.SWAPPED

        # Audit event
        db.add(EscrowEvent(
            order_id=order.id,
            event_type="SWAP_EXECUTED",
            payload={
                "usdc_input": str(usdc_amount),
                "usdt_output": str(swap_res.output_amount_usdt),
                "fee_usdt": str(swap_res.fee_amount_usdt),
                "reference": swap_res.reference,
                "rate": str(swap_res.rate) if swap_res.rate else None,
            },
        ))

        await db.commit()
        return swap
