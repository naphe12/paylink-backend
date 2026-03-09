from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.p2p_enums import OfferSide, TokenCode
from app.models.p2p_offer import P2POffer


class P2PMatchingEngine:
    @staticmethod
    async def best_offer(
        db: AsyncSession,
        token: TokenCode,
        side: OfferSide,
        token_amount,
        exclude_user_id=None,
    ) -> P2POffer | None:
        # BUY order wants to buy => match a SELL offer.
        # SELL order wants to sell => match a BUY offer.
        target_side = OfferSide.SELL if side == OfferSide.BUY else OfferSide.BUY

        stmt = (
            select(P2POffer)
            .where(
                P2POffer.is_active.is_(True),
                P2POffer.token == token,
                P2POffer.side == target_side,
                P2POffer.available_amount >= token_amount,
            )
        )
        if exclude_user_id is not None:
            stmt = stmt.where(P2POffer.user_id != exclude_user_id)

        # If user buys, prefer the lowest price.
        # If user sells, prefer the highest price.
        if side == OfferSide.BUY:
            stmt = stmt.order_by(P2POffer.price_bif_per_usd.asc(), P2POffer.created_at.asc())
        else:
            stmt = stmt.order_by(P2POffer.price_bif_per_usd.desc(), P2POffer.created_at.asc())

        return await db.scalar(stmt)
