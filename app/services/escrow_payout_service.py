from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.escrow_order import EscrowOrder
from models.escrow_payout import EscrowPayout
from models.escrow_event import EscrowEvent
from models.escrow_enums import EscrowOrderStatus
from services.payout_port import PayoutProvider

class EscrowPayoutService:
    def __init__(self, provider: PayoutProvider):
        self.provider = provider

    async def execute_payout(self, db: AsyncSession, order_id: str):
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order or order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise ValueError("Order not ready for payout")

        result = await self.provider.send_bif(
            float(order.bif_target),
            {
                "provider": order.payout_provider,
                "account": order.payout_account_number,
                "name": order.payout_account_name,
            }
        )

        payout = EscrowPayout(
            order_id=order.id,
            method=order.payout_method,
            provider=order.payout_provider,
            account_name=order.payout_account_name,
            account_number=order.payout_account_number,
            amount_bif=order.bif_target,
            reference=result.reference,
            status="CONFIRMED",
            initiated_at=order.payout_initiated_at or datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(payout)

        order.bif_paid = order.bif_target
        order.paid_out_at = datetime.now(timezone.utc)
        order.status = EscrowOrderStatus.PAID_OUT

        db.add(EscrowEvent(
            order_id=order.id,
            event_type="AUTO_PAYOUT_CONFIRMED",
            payload={"reference": result.reference},
        ))
        await db.commit()
