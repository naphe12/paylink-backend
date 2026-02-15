from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.p2p_offer import P2POffer
from app.schemas.p2p_offer import OfferCreate

class P2POfferService:
    @staticmethod
    async def create_offer(db: AsyncSession, user_id, data: OfferCreate) -> P2POffer:
        offer = P2POffer(
            user_id=user_id,
            side=data.side,
            token=data.token,
            price_bif_per_usd=data.price_bif_per_usd,
            min_token_amount=data.min_token_amount,
            max_token_amount=data.max_token_amount,
            available_amount=data.available_amount,
            payment_method=data.payment_method,
            payment_details=data.payment_details,
            terms=data.terms,
        )
        db.add(offer)
        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def list_offers(db: AsyncSession, token=None, side=None, active=True):
        stmt = select(P2POffer)
        if active is not None:
            stmt = stmt.where(P2POffer.is_active == active)
        if token:
            stmt = stmt.where(P2POffer.token == token)
        if side:
            stmt = stmt.where(P2POffer.side == side)
        res = await db.execute(stmt.order_by(P2POffer.created_at.desc()))
        return list(res.scalars().all())
