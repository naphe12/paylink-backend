from sqlalchemy.ext.asyncio import AsyncSession
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory
from app.models.p2p_enums import TradeStatus
from app.services.p2p_agent_email_service import notify_agent_fiat_confirmation_needed
from app.services.p2p_trade_rules import validate_trade_transition

async def set_trade_status(
    db: AsyncSession,
    trade: P2PTrade,
    to_status: TradeStatus,
    actor_user_id,
    actor_role: str,
    note: str | None = None,
):
    from_status = trade.status
    validate_trade_transition(from_status, to_status)
    trade.status = to_status

    db.add(P2PTradeStatusHistory(
        trade_id=trade.trade_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        note=note,
    ))

    if to_status == TradeStatus.CRYPTO_LOCKED:
        await notify_agent_fiat_confirmation_needed(db, trade)
