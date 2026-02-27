from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.dependencies.kill_switch import require_not_killed
from app.models.p2p_enums import OfferSide, PaymentMethod, TokenCode, TradeStatus
from app.models.p2p_offer import P2POffer
from app.models.users import Users
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory

from app.schemas.p2p_offer import OfferCreate, OfferOut
from app.schemas.p2p_trade import TradeCreate, TradeOut, FiatSentIn, DisputeOpenIn
from app.services.p2p_offer_service import P2POfferService
from app.services.p2p_matching_engine import P2PMatchingEngine
from app.services.p2p_mm_quote import P2PMMQuote
from app.services.liquidity_guard import LiquidityGuard
from app.services.audit import audit
from app.services.p2p_trade_state import set_trade_status
from app.services.p2p_trade_service import P2PTradeService
from app.services.p2p_dispute_service import P2PDisputeService

router = APIRouter(prefix="/p2p", tags=["P2P"])


class SandboxCryptoLockedIn(BaseModel):
    escrow_tx_hash: str | None = None

@router.get("/offers", response_model=list[OfferOut])
async def list_offers(token: str | None = None, side: str | None = None, db: AsyncSession = Depends(get_db)):
    # token/side can be validated stricter if you want
    return await P2POfferService.list_offers(db, token=token, side=side, active=True)

@router.post("/offers", response_model=OfferOut)
async def create_offer(
    data: OfferCreate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    _: None = Depends(require_not_killed),
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
    _: None = Depends(require_not_killed),
):
    try:
        return await P2PTradeService.create_trade(db, me.user_id, data)
    except PermissionError as e:
        raise HTTPException(403, str(e))
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
async def market_order(
    token: TokenCode,
    side: OfferSide,
    token_amount: Decimal,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    _: None = Depends(require_not_killed),
):
    try:
        offer = await P2PMatchingEngine.best_offer(
            db=db,
            token=token,
            side=side,
            token_amount=token_amount,
        )
        if offer:
            return await P2PTradeService.create_trade(
                db, me.user_id, TradeCreate(offer_id=offer.offer_id, token_amount=token_amount)
            )

        # fallback MM
        if not settings.P2P_MM_ENABLED:
            raise HTTPException(400, "No matching offer and MM disabled")
        if not settings.SYSTEM_TREASURY_USER_ID:
            raise HTTPException(400, "SYSTEM_TREASURY_USER_ID not set")

        # base price = median book
        median_stmt = select(func.percentile_cont(0.5).within_group(P2POffer.price_bif_per_usd)).where(
            P2POffer.token == token,
            P2POffer.is_active.is_(True),
        )
        median = (await db.execute(median_stmt)).scalar()
        if not median:
            raise HTTPException(400, "No reference price available for MM")
        mm_price = P2PMMQuote.quote_price(Decimal(median), side.value)

        # Treasury guard before MM fallback
        if side == OfferSide.BUY:
            # User buys token -> system must be able to deliver token
            await LiquidityGuard.assert_balance(
                db,
                account_code=f"TREASURY_{token.value}",
                token=token.value,
                required_amount=token_amount,
            )
        else:
            # User sells token -> system must be able to pay BIF
            bif_required = token_amount * mm_price
            await LiquidityGuard.assert_balance(
                db,
                account_code="TREASURY_BIF",
                token="BIF",
                required_amount=bif_required,
            )

        mm_offer = await P2POfferService.create_offer(
            db,
            user_id=settings.SYSTEM_TREASURY_USER_ID,
            data=OfferCreate(
                side=OfferSide.SELL if side == OfferSide.BUY else OfferSide.BUY,
                token=token,
                price_bif_per_usd=mm_price,
                min_token_amount=token_amount,
                max_token_amount=token_amount,
                available_amount=token_amount,
                payment_method=PaymentMethod.OTHER,
                payment_details={"mode": "MM"},
                terms="Market Maker",
            ),
        )
        trade = await P2PTradeService.create_trade(
            db, me.user_id, TradeCreate(offer_id=mm_offer.offer_id, token_amount=token_amount)
        )
        await audit(
            db,
            actor_user_id=me.user_id,
            actor_role=str(me.role),
            action="P2P_MM_FALLBACK",
            entity_type="P2P_TRADE",
            entity_id=str(trade.trade_id),
            metadata={
                "token": token.value,
                "side": side.value,
                "token_amount": str(token_amount),
                "mm_price_bif_per_usd": str(mm_price),
                "offer_id": str(mm_offer.offer_id),
            },
        )
        await db.commit()
        return trade
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/trades/{trade_id}/sandbox/crypto-locked", response_model=TradeOut)
async def sandbox_crypto_locked(
    trade_id: str,
    data: SandboxCryptoLockedIn | None = None,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    try:
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise HTTPException(404, "Trade not found")

        if trade.status == TradeStatus.CRYPTO_LOCKED:
            return trade
        if trade.status != TradeStatus.AWAITING_CRYPTO:
            raise HTTPException(400, f"Trade not in AWAITING_CRYPTO (current={trade.status.value})")

        trade.escrow_tx_hash = (data.escrow_tx_hash if data and data.escrow_tx_hash else f"0xsandbox{uuid4().hex}")
        trade.escrow_locked_at = datetime.now(timezone.utc)
        await set_trade_status(
            db,
            trade,
            TradeStatus.CRYPTO_LOCKED,
            actor_user_id=None,
            actor_role="ADMIN",
            note="Sandbox forced crypto lock",
        )
        await db.commit()
        await db.refresh(trade)
        return trade
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
