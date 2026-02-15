from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.p2p_dispute import P2PDispute
from app.models.p2p_trade import P2PTrade
from app.models.p2p_enums import TradeStatus, DisputeStatus
from app.services.p2p_trade_state import set_trade_status

class P2PDisputeService:
    @staticmethod
    async def open_dispute(db: AsyncSession, trade_id, opened_by, reason: str) -> P2PDispute:
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise ValueError("Trade not found")

        if opened_by not in (trade.buyer_id, trade.seller_id):
            raise PermissionError("Not a party of this trade")

        dispute = P2PDispute(trade_id=trade.trade_id, opened_by=opened_by, reason=reason, status=DisputeStatus.OPEN)
        db.add(dispute)
        await set_trade_status(db, trade, TradeStatus.DISPUTED, opened_by, "CLIENT", note="Dispute opened")

        await db.commit()
        await db.refresh(dispute)
        return dispute
