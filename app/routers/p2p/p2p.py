import hashlib
import hmac
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict
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

from app.schemas.p2p_offer import OfferCreate, OfferOut, OfferUpdate
from app.schemas.p2p_trade import TradeCreate, TradeOut, FiatSentIn, DisputeOpenIn, DisputeResolveIn
from app.services.p2p_offer_service import P2POfferService
from app.services.p2p_matching_engine import P2PMatchingEngine
from app.services.p2p_mm_quote import P2PMMQuote
from app.services.liquidity_guard import LiquidityGuard
from app.services.audit import audit
from app.services.p2p_chain_webhook_service import process_p2p_chain_deposit_webhook
from app.services.p2p_trade_state import set_trade_status
from app.services.p2p_trade_service import P2PTradeService
from app.services.p2p_dispute_service import P2PDisputeService
from app.security.rate_limit import rate_limit
from app.services.webhook_log_service import log_webhook
from app.core.security import decode_access_token
from app.services.idempotency_service import (
    acquire_idempotency,
    compute_request_hash,
    store_idempotency_response,
)
from app.dependencies.step_up import get_admin_step_up_method, require_admin_step_up

router = APIRouter(prefix="/p2p", tags=["P2P"])

class SandboxCryptoLockedIn(BaseModel):
    escrow_tx_hash: str | None = None


class P2PChainDepositWebhookIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    network: str
    tx_hash: str
    log_index: int = 0
    from_address: str | None = None
    to_address: str
    amount: Decimal
    confirmations: int = 0
    token_symbol: str | None = None
    token_address: str | None = None
    amount_raw: str | None = None
    block_number: int | None = None
    block_timestamp: int | None = None
    chain_id: int | None = None
    escrow_deposit_ref: str | None = None
    provider: str | None = None
    provider_event_id: str | None = None
    source: str | None = None
    source_ref: str | None = None

@router.get("/offers", response_model=list[OfferOut])
async def list_offers(token: str | None = None, side: str | None = None, db: AsyncSession = Depends(get_db)):
    # token/side can be validated stricter if you want
    return await P2POfferService.list_offers(db, token=token, side=side, active=True)

@router.get("/offers/mine", response_model=list[OfferOut])
async def list_my_offers(
    active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    return await P2POfferService.list_user_offers(db, me.user_id, active=active)

@router.post("/offers", response_model=OfferOut)
async def create_offer(
    data: OfferCreate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    _: None = Depends(require_not_killed),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            payload_hash = compute_request_hash(
                {
                    "side": str(data.side.value if hasattr(data.side, "value") else data.side),
                    "token": str(data.token.value if hasattr(data.token, "value") else data.token),
                    "price_bif_per_usd": str(data.price_bif_per_usd),
                    "min_token_amount": str(data.min_token_amount),
                    "max_token_amount": str(data.max_token_amount),
                    "available_amount": str(data.available_amount),
                    "payment_method": str(data.payment_method.value if hasattr(data.payment_method, "value") else data.payment_method),
                    "terms": str(data.terms or ""),
                }
            )
            scoped_idempotency_key = f"p2p_create_offer:{me.user_id}:{idempotency_key.strip()}"
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        created = await P2POfferService.create_offer(db, me.user_id, data)
        if scoped_idempotency_key:
            payload_out = OfferOut.model_validate(created).model_dump(mode="json")
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=payload_out,
            )
            await db.commit()
            return payload_out
        return created
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades", response_model=TradeOut)
async def create_trade(
    data: TradeCreate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    _: None = Depends(require_not_killed),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            payload_hash = compute_request_hash(
                {
                    "offer_id": str(data.offer_id),
                    "token_amount": str(data.token_amount),
                }
            )
            scoped_idempotency_key = f"p2p_create_trade:{me.user_id}:{idempotency_key.strip()}"
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        created = await P2PTradeService.create_trade(db, me.user_id, data)
        if scoped_idempotency_key:
            payload_out = TradeOut.model_validate(created).model_dump(mode="json")
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=payload_out,
            )
            await db.commit()
            return payload_out
        return created
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/webhooks/chain-deposit")
async def p2p_chain_deposit_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:p2p_chain_webhook", limit=60, window_seconds=60)

    raw_body = await request.body()
    signature = request.headers.get("X-Paylink-Signature")
    secret = settings.HMAC_SECRET or settings.ESCROW_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = P2PChainDepositWebhookIn.model_validate(await request.json())
    payload_data = payload.model_dump(mode="json", exclude_none=True)

    try:
        result = await process_p2p_chain_deposit_webhook(db, payload_data)
        result_status = str((result or {}).get("status") or "SUCCESS").upper()
        await log_webhook(
            db,
            event_type="P2P_CHAIN_DEPOSIT",
            status=result_status,
            payload=payload_data,
            tx_hash=payload.tx_hash,
            network=payload.network,
        )
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        try:
            await log_webhook(
                db,
                event_type="P2P_CHAIN_DEPOSIT",
                status="FAILED",
                payload=payload_data,
                tx_hash=payload.tx_hash,
                network=payload.network,
                error=str(exc),
            )
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/offers/{offer_id}", response_model=OfferOut)
async def get_offer(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    offer = await P2POfferService.get_offer(db, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    if me.role != "admin" and str(offer.user_id) != str(me.user_id):
        raise HTTPException(403, "Forbidden")
    return offer


@router.patch("/offers/{offer_id}", response_model=OfferOut)
async def update_offer(
    offer_id: str,
    data: OfferUpdate,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    _: None = Depends(require_not_killed),
):
    try:
        return await P2POfferService.update_offer(db, me.user_id, offer_id, data)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/offers/{offer_id}/deactivate", response_model=OfferOut)
async def deactivate_offer(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2POfferService.set_offer_active(db, me.user_id, offer_id, False)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/offers/{offer_id}/activate", response_model=OfferOut)
async def activate_offer(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2POfferService.set_offer_active(db, me.user_id, offer_id, True)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/offers/{offer_id}")
async def delete_offer(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        await P2POfferService.delete_offer(db, me.user_id, offer_id)
        return {"status": "OK"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/trades/mine", response_model=list[TradeOut])
async def list_my_trades(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    try:
        return await P2PTradeService.list_user_trades(db, me.user_id, status=status)
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            payload_hash = compute_request_hash(
                {
                    "token": token.value,
                    "side": side.value,
                    "token_amount": str(token_amount),
                }
            )
            scoped_idempotency_key = f"p2p_market_order:{me.user_id}:{idempotency_key.strip()}"
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        offer = await P2PMatchingEngine.best_offer(
            db=db,
            token=token,
            side=side,
            token_amount=token_amount,
            exclude_user_id=me.user_id,
        )
        if offer:
            created = await P2PTradeService.create_trade(
                db, me.user_id, TradeCreate(offer_id=offer.offer_id, token_amount=token_amount)
            )
            if scoped_idempotency_key:
                payload_out = TradeOut.model_validate(created).model_dump(mode="json")
                await store_idempotency_response(
                    db,
                    key=scoped_idempotency_key,
                    status_code=200,
                    payload=payload_out,
                )
                await db.commit()
                return payload_out
            return created

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
        if scoped_idempotency_key:
            payload_out = TradeOut.model_validate(trade).model_dump(mode="json")
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=payload_out,
            )
            await db.commit()
            return payload_out
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
        if trade.status not in (TradeStatus.AWAITING_CRYPTO, TradeStatus.EXPIRED):
            raise HTTPException(400, f"Trade not in AWAITING_CRYPTO/EXPIRED (current={trade.status.value})")

        trade.escrow_tx_hash = (data.escrow_tx_hash if data and data.escrow_tx_hash else f"0xsandbox{uuid4().hex}")
        trade.escrow_locked_at = datetime.now(timezone.utc)
        note = "Sandbox forced crypto lock"
        if trade.status == TradeStatus.EXPIRED:
            note = "Sandbox forced crypto lock (override from EXPIRED)"
        await set_trade_status(
            db,
            trade,
            TradeStatus.CRYPTO_LOCKED,
            actor_user_id=None,
            actor_role="ADMIN",
            note=note,
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            scoped_idempotency_key = f"p2p_fiat_sent:{trade_id}:{me.user_id}:{idempotency_key.strip()}"
            payload_hash = compute_request_hash(
                {
                    "action": "p2p_fiat_sent",
                    "trade_id": str(trade_id),
                    "actor_id": str(me.user_id),
                    "proof_url": str(data.proof_url or ""),
                    "note": str(data.note or ""),
                }
            )
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        updated = await P2PTradeService.mark_fiat_sent(db, trade_id, me.user_id, data)
        if scoped_idempotency_key:
            payload_out = TradeOut.model_validate(updated).model_dump(mode="json")
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=payload_out,
            )
            await db.commit()
            return payload_out
        return updated
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/trades/{trade_id}/fiat-sent-by-agent", response_model=TradeOut)
async def fiat_sent_by_agent_link(
    trade_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_access_token(token)
        if payload.get("action") != "p2p_fiat_sent_by_agent":
            raise HTTPException(403, "Invalid token action")
        if str(payload.get("trade_id") or "") != str(trade_id):
            raise HTTPException(403, "Token trade mismatch")

        actor_user_id = str(payload.get("sub") or "").strip()
        if not actor_user_id:
            raise HTTPException(403, "Invalid token subject")

        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise HTTPException(404, "Trade not found")

        if str(trade.seller_id) != actor_user_id:
            raise HTTPException(403, "Only assigned seller can confirm BIF payment")

        if trade.status in (TradeStatus.FIAT_SENT, TradeStatus.FIAT_CONFIRMED, TradeStatus.RELEASED):
            # Idempotent behavior: link can be clicked multiple times safely.
            return trade

        if trade.status not in (TradeStatus.AWAITING_FIAT, TradeStatus.CRYPTO_LOCKED):
            raise HTTPException(400, f"Trade not ready for fiat sent (current={trade.status.value})")

        if trade.status == TradeStatus.CRYPTO_LOCKED:
            await set_trade_status(
                db,
                trade,
                TradeStatus.AWAITING_FIAT,
                actor_user_id=actor_user_id,
                actor_role="AGENT_LINK",
                note="Trade ready for fiat payment via email link",
            )

        trade.fiat_sent_at = datetime.now(timezone.utc)
        await set_trade_status(
            db,
            trade,
            TradeStatus.FIAT_SENT,
            actor_user_id=actor_user_id,
            actor_role="AGENT_LINK",
            note="BIF payment confirmed via email link",
        )
        await db.commit()
        await db.refresh(trade)
        return trade
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/trades/{trade_id}/fiat-confirm", response_model=TradeOut)
async def fiat_confirm(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            scoped_idempotency_key = f"p2p_fiat_confirm:{trade_id}:{me.user_id}:{idempotency_key.strip()}"
            payload_hash = compute_request_hash(
                {
                    "action": "p2p_fiat_confirm",
                    "trade_id": str(trade_id),
                    "actor_id": str(me.user_id),
                }
            )
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        updated = await P2PTradeService.confirm_fiat_received(db, trade_id, me.user_id)
        if scoped_idempotency_key:
            payload_out = TradeOut.model_validate(updated).model_dump(mode="json")
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=payload_out,
            )
            await db.commit()
            return payload_out
        return updated
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        scoped_idempotency_key = None
        if idempotency_key and idempotency_key.strip():
            scoped_idempotency_key = f"p2p_open_dispute:{trade_id}:{me.user_id}:{idempotency_key.strip()}"
            payload_hash = compute_request_hash(
                {
                    "action": "p2p_open_dispute",
                    "trade_id": str(trade_id),
                    "actor_id": str(me.user_id),
                    "reason": str(data.reason or ""),
                }
            )
            idem = await acquire_idempotency(
                db,
                key=scoped_idempotency_key,
                request_hash=payload_hash,
            )
            if idem.conflict:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key deja utilisee avec un payload different.",
                )
            if idem.replay_payload is not None:
                return idem.replay_payload
            if idem.in_progress:
                raise HTTPException(
                    status_code=409,
                    detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
                )
        dispute = await P2PDisputeService.open_dispute(
            db,
            trade_id,
            me.user_id,
            data.reason,
            reason_code=data.reason_code,
            proof_type=data.proof_type,
            proof_ref=data.proof_ref,
        )
        response_payload = {"status": "OK", "dispute_id": str(dispute.dispute_id)}
        if scoped_idempotency_key:
            await store_idempotency_response(
                db,
                key=scoped_idempotency_key,
                status_code=200,
                payload=response_payload,
            )
            await db.commit()
        return response_payload
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/trades/{trade_id}/dispute/resolve")
async def resolve_dispute(
    trade_id: str,
    data: DisputeResolveIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(require_admin_step_up("p2p_dispute_resolve")),
):
    try:
        dispute = await P2PDisputeService.resolve_dispute(
            db,
            trade_id=trade_id,
            resolved_by=me.user_id,
            outcome=data.outcome,
            resolution=data.resolution,
            resolution_code=data.resolution_code,
            proof_type=data.proof_type,
            proof_ref=data.proof_ref,
            step_up_method=get_admin_step_up_method(request),
        )
        return {
            "status": "OK",
            "dispute_id": str(dispute.dispute_id),
            "dispute_status": str(getattr(dispute.status, "value", dispute.status)),
            "trade_id": trade_id,
            "outcome": data.outcome,
        }
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))
