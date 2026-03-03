from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.p2p_enums import TradeStatus
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.schemas.p2p_offer import OfferCreate
from app.schemas.p2p_offer import OfferUpdate

class P2POfferService:
    MUTATION_BLOCKING_STATUSES = (
        TradeStatus.CREATED,
        TradeStatus.AWAITING_CRYPTO,
        TradeStatus.CRYPTO_LOCKED,
        TradeStatus.AWAITING_FIAT,
        TradeStatus.FIAT_SENT,
        TradeStatus.FIAT_CONFIRMED,
        TradeStatus.DISPUTED,
    )

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
    async def get_offer(db: AsyncSession, offer_id) -> P2POffer | None:
        return await db.scalar(select(P2POffer).where(P2POffer.offer_id == offer_id))

    @staticmethod
    async def list_user_offers(db: AsyncSession, user_id, active=None):
        stmt = select(P2POffer).where(P2POffer.user_id == user_id)
        if active is not None:
            stmt = stmt.where(P2POffer.is_active == active)
        res = await db.execute(stmt.order_by(P2POffer.created_at.desc()))
        return list(res.scalars().all())

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

    @staticmethod
    async def _get_owned_offer(db: AsyncSession, user_id, offer_id) -> P2POffer:
        offer = await db.scalar(
            select(P2POffer).where(
                P2POffer.offer_id == offer_id,
                P2POffer.user_id == user_id,
            )
        )
        if not offer:
            raise ValueError("Offer not found")
        return offer

    @staticmethod
    async def _assert_no_open_trades(db: AsyncSession, offer_id) -> None:
        blocking_trade = await db.scalar(
            select(P2PTrade).where(
                P2PTrade.offer_id == offer_id,
                P2PTrade.status.in_(P2POfferService.MUTATION_BLOCKING_STATUSES),
            )
        )
        if blocking_trade:
            raise ValueError("Offer cannot be modified while a trade is still open")

    @staticmethod
    async def update_offer(db: AsyncSession, user_id, offer_id, data: OfferUpdate) -> P2POffer:
        offer = await P2POfferService._get_owned_offer(db, user_id, offer_id)
        await P2POfferService._assert_no_open_trades(db, offer.offer_id)

        offer.side = data.side
        offer.token = data.token
        offer.price_bif_per_usd = data.price_bif_per_usd
        offer.min_token_amount = data.min_token_amount
        offer.max_token_amount = data.max_token_amount
        offer.available_amount = Decimal(str(data.available_amount))
        offer.payment_method = data.payment_method
        offer.payment_details = data.payment_details
        offer.terms = data.terms

        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def set_offer_active(db: AsyncSession, user_id, offer_id, is_active: bool) -> P2POffer:
        offer = await P2POfferService._get_owned_offer(db, user_id, offer_id)
        if not is_active:
            await P2POfferService._assert_no_open_trades(db, offer.offer_id)
        offer.is_active = is_active
        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def delete_offer(db: AsyncSession, user_id, offer_id) -> None:
        offer = await P2POfferService._get_owned_offer(db, user_id, offer_id)
        await P2POfferService._assert_no_open_trades(db, offer.offer_id)
        await db.delete(offer)
        await db.commit()
