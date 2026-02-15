from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory

from app.schemas.p2p_offer import OfferCreate, OfferOut
from app.schemas.p2p_trade import TradeCreate, TradeOut, FiatSentIn, DisputeOpenIn, MarketOrderIn
from app.services.p2p_offer_service import P2POfferService
from app.services.p2p_matching_engine import P2PMatchingEngine
from app.services.p2p_trade_service import P2PTradeService
from app.services.p2p_dispute_service import P2PDisputeService

router = APIRouter(prefix="/p2p", tags=["P2P"])

@router.get("/offers", response_model=list[OfferOut])
async def list_offers(token: str | None = None, side: str | None = None, db: AsyncSession = Depends(get_db)):
    # token/side can be validated stricter if you want
    return await P2POfferService.list_offers(db, token=token, side=side, active=True)

@router.post("/offers", response_model=OfferOut)
async def create_offer(
    data: OfferCreate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2POfferService.create_offer(db, me.user_id, data)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades", response_model=TradeOut)
async def create_trade(
    data: TradeCreate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2PTradeService.create_trade(db, me.user_id, data)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/trades/{trade_id}", response_model=TradeOut)
async def get_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
    if not trade:
        raise HTTPException(404, "Trade not found")

    # Access limited to trade parties unless admin.
    if me.role != "admin" and me.user_id not in (trade.buyer_id, trade.seller_id):
        raise HTTPException(403, "Forbidden")

    return trade


@router.get("/trades/{trade_id}/timeline")
async def get_trade_timeline(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    stmt = (
        select(P2PTradeStatusHistory)
        .where(P2PTradeStatusHistory.trade_id == trade_id)
        .order_by(P2PTradeStatusHistory.created_at.asc())
    )

    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/market-order", response_model=TradeOut)
async def create_market_order(
    data: MarketOrderIn,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        offer = await P2PMatchingEngine.best_offer(
            db=db,
            token=data.token,
            side=data.side,
            token_amount=data.token_amount,
        )
        if not offer:
            raise HTTPException(404, "No matching offer found")

        trade_in = TradeCreate(offer_id=offer.offer_id, token_amount=data.token_amount)
        return await P2PTradeService.create_trade(db, me.user_id, trade_in)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades/{trade_id}/fiat-sent", response_model=TradeOut)
async def fiat_sent(
    trade_id: str,
    data: FiatSentIn,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2PTradeService.mark_fiat_sent(db, trade_id, me.user_id, data)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades/{trade_id}/fiat-confirm", response_model=TradeOut)
async def fiat_confirm(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2PTradeService.confirm_fiat_received(db, trade_id, me.user_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades/{trade_id}/dispute")
async def open_dispute(
    trade_id: str,
    data: DisputeOpenIn,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        dispute = await P2PDisputeService.open_dispute(db, trade_id, me.user_id, data.reason)
        return {"status": "OK", "dispute_id": str(dispute.dispute_id)}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))
