from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory
from app.models.p2p_enums import TradeStatus

async def set_trade_status(
    db: AsyncSession,
    trade: P2PTrade,
    to_status: TradeStatus,
    actor_user_id,
    actor_role: str,
    note: str | None = None,
):
    from_status = trade.status
    trade.status = to_status

    db.add(P2PTradeStatusHistory(
        trade_id=trade.trade_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        note=note,
    ))
