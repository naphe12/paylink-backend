from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.escrow_order import EscrowOrder
from models.escrow_enums import EscrowOrderStatus

class EscrowService:

    @staticmethod
    async def create_order(db: AsyncSession, order: EscrowOrder) -> EscrowOrder:
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def get_order(db: AsyncSession, order_id: str) -> EscrowOrder:
        res = await db.execute(
            select(EscrowOrder).where(EscrowOrder.id == order_id)
        )
        order = res.scalar_one_or_none()
        if not order:
            raise ValueError("Escrow order not found")
        return order

    @staticmethod
    async def mark_funded(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.CREATED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.FUNDED
        await db.commit()

    @staticmethod
    async def mark_swapped(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.FUNDED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.SWAPPED
        await db.commit()

    @staticmethod
    async def mark_payout_pending(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.SWAPPED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.PAYOUT_PENDING
        await db.commit()

    @staticmethod
    async def mark_paid_out(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.PAID_OUT
        await db.commit()
