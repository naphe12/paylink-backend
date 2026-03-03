from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.p2p_enums import TradeStatus
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.services.p2p_trade_state import set_trade_status


EXPIRABLE_STATUSES = (
    TradeStatus.AWAITING_CRYPTO,
    TradeStatus.AWAITING_FIAT,
)


async def run_p2p_expiration_worker(db: AsyncSession) -> int:
    now_utc = datetime.now(timezone.utc)
    stmt = select(P2PTrade).where(
        P2PTrade.status.in_(EXPIRABLE_STATUSES),
        P2PTrade.expires_at <= now_utc,
    )
    trades = list((await db.execute(stmt)).scalars().all())
    if not trades:
        return 0

    expired_count = 0
    for trade in trades:
        offer = await db.scalar(select(P2POffer).where(P2POffer.offer_id == trade.offer_id))
        if offer:
            offer.available_amount = (
                Decimal(str(offer.available_amount or 0)) + Decimal(str(trade.token_amount or 0))
            ).quantize(Decimal("0.00000001"))

        await set_trade_status(
            db,
            trade,
            TradeStatus.EXPIRED,
            actor_user_id=None,
            actor_role="SYSTEM",
            note="Trade expired automatically",
        )
        expired_count += 1

    await db.commit()
    return expired_count
