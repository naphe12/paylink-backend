from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.models.p2p_payment_proof import P2PPaymentProof
from app.models.p2p_enums import TradeStatus
from app.models.users import Users
from app.schemas.p2p_trade import TradeCreate, FiatSentIn
from app.services.alerts import deliver_alerts
from app.services.aml_engine import AMLEngine
from app.services.p2p_escrow_allocator import P2PEscrowAllocator
from app.services.p2p_fee_engine import P2PFeeEngine
from app.services.p2p_ledger_hooks import ledger_fee, ledger_release
from app.services.metrics import inc
from app.services.p2p_risk_service import P2PRiskService
from app.services.p2p_release_service import release_crypto_to_buyer
from app.services.p2p_trade_state import set_trade_status

class P2PTradeService:
    DEFAULT_TTL_MINUTES = 30

    @staticmethod
    async def create_trade(db: AsyncSession, buyer_id, data: TradeCreate) -> P2PTrade:
        offer = await db.scalar(select(P2POffer).where(P2POffer.offer_id == data.offer_id))
        if not offer or not offer.is_active:
            raise ValueError("Offer not found or inactive")
        if str(offer.user_id) == str(buyer_id):
            raise PermissionError("You cannot create a trade on your own offer")

        if data.token_amount < offer.min_token_amount or data.token_amount > offer.max_token_amount:
            raise ValueError("Amount outside offer limits")

        if data.token_amount > offer.available_amount:
            raise ValueError("Not enough liquidity on this offer")

        # Determine buyer/seller by side
        if offer.side.value == "SELL":
            seller_id = offer.user_id
            buyer = buyer_id
            buyer_id_ = buyer
            seller_id_ = seller_id
            # SELL offer => seller must deposit crypto then buyer pays BIF
            initial_status = TradeStatus.AWAITING_CRYPTO
        else:
            # BUY offer => offer owner is buyer; matcher is seller
            buyer_id_ = offer.user_id
            seller_id_ = buyer_id
            initial_status = TradeStatus.AWAITING_CRYPTO  # still require seller to deposit crypto
        price = Decimal(offer.price_bif_per_usd)
        bif_amount = (Decimal(data.token_amount) * price).quantize(Decimal("0.01"))

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=P2PTradeService.DEFAULT_TTL_MINUTES)

        trade = P2PTrade(
            offer_id=offer.offer_id,
            buyer_id=buyer_id_,
            seller_id=seller_id_,
            token=offer.token,
            token_amount=data.token_amount,
            price_bif_per_usd=offer.price_bif_per_usd,
            bif_amount=bif_amount,
            status=initial_status,
            payment_method=offer.payment_method,
            expires_at=expires_at,
            escrow_network=None,
            escrow_deposit_addr=None,  # filled by your escrow address allocator
        )

        # Reserve offer liquidity immediately
        offer.available_amount = (Decimal(offer.available_amount) - Decimal(data.token_amount))

        db.add(trade)
        await db.flush()
        await P2PEscrowAllocator.allocate_address(db, trade)
        await set_trade_status(db, trade, initial_status, actor_user_id=buyer_id, actor_role="CLIENT", note="Trade created")
        await P2PRiskService.apply(db, trade)
        aml = await AMLEngine.evaluate_p2p(db, trade, event="P2P_CREATE")
        trade.risk_score = aml["final_score"]
        trade.flags = sorted(set(list(trade.flags or []) + [h["code"] for h in aml["hits"]]))

        if aml["should_alert"]:
            await deliver_alerts(
                db,
                subject="AML Alert (P2P_CREATE)",
                message=f"Trade {trade.trade_id} AML score {aml['final_score']}",
                metadata={"trade_id": str(trade.trade_id), "event": "P2P_CREATE", "hits": aml["hits"]},
            )
        inc("p2p.trade.created")

        await db.commit()
        await db.refresh(trade)
        return trade

    @staticmethod
    async def list_user_trades(db: AsyncSession, user_id, status: str | None = None) -> list[P2PTrade]:
        stmt = select(P2PTrade).where(
            (P2PTrade.buyer_id == user_id) | (P2PTrade.seller_id == user_id)
        )
        if status == "open":
            stmt = stmt.where(
                P2PTrade.status.in_(
                    (
                        TradeStatus.CREATED,
                        TradeStatus.AWAITING_CRYPTO,
                        TradeStatus.CRYPTO_LOCKED,
                        TradeStatus.AWAITING_FIAT,
                        TradeStatus.FIAT_SENT,
                        TradeStatus.FIAT_CONFIRMED,
                        TradeStatus.DISPUTED,
                    )
                )
            )
        elif status == "closed":
            stmt = stmt.where(
                P2PTrade.status.in_(
                    (
                        TradeStatus.RELEASED,
                        TradeStatus.CANCELLED,
                        TradeStatus.EXPIRED,
                        TradeStatus.RESOLVED,
                    )
                )
            )
        elif status:
            stmt = stmt.where(P2PTrade.status == TradeStatus(status))

        res = await db.execute(stmt.order_by(P2PTrade.created_at.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def mark_fiat_sent(db: AsyncSession, trade_id, actor_user_id, data: FiatSentIn):
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise ValueError("Trade not found")

        # Only buyer can mark paid
        if trade.buyer_id != actor_user_id:
            raise PermissionError("Only buyer can mark fiat sent")

        if trade.status not in (TradeStatus.AWAITING_FIAT, TradeStatus.CRYPTO_LOCKED):
            raise ValueError("Trade not ready for fiat payment")

        proof = P2PPaymentProof(
            trade_id=trade.trade_id,
            actor_user_id=actor_user_id,
            kind="FIAT_PROOF",
            url=data.proof_url,
            metadata_={"note": data.note} if data.note else {},
        )
        db.add(proof)

        if trade.status == TradeStatus.CRYPTO_LOCKED:
            await set_trade_status(
                db,
                trade,
                TradeStatus.AWAITING_FIAT,
                actor_user_id,
                "CLIENT",
                note="Trade ready for fiat payment",
            )

        trade.fiat_sent_at = datetime.now(timezone.utc)
        await set_trade_status(db, trade, TradeStatus.FIAT_SENT, actor_user_id, "CLIENT", note="Buyer marked fiat sent")
        await P2PRiskService.apply(db, trade)
        aml = await AMLEngine.evaluate_p2p(db, trade, event="P2P_FIAT_SENT")
        trade.risk_score = aml["final_score"]
        trade.flags = sorted(set(list(trade.flags or []) + [h["code"] for h in aml["hits"]]))
        if aml["should_alert"]:
            await deliver_alerts(
                db,
                subject="AML Alert (P2P_FIAT_SENT)",
                message=f"Trade {trade.trade_id} AML score {aml['final_score']}",
                metadata={
                    "trade_id": str(trade.trade_id),
                    "event": "P2P_FIAT_SENT",
                    "hits": aml["hits"],
                },
            )
        inc("p2p.trade.fiat_sent")

        await db.commit()
        await db.refresh(trade)
        return trade

    @staticmethod
    async def confirm_fiat_received(db: AsyncSession, trade_id, actor_user_id):
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise ValueError("Trade not found")

        if trade.seller_id != actor_user_id:
            raise PermissionError("Only seller can confirm receiving fiat")

        if trade.status != TradeStatus.FIAT_SENT:
            raise ValueError("Trade not in FIAT_SENT")

        trade.fiat_confirmed_at = datetime.now(timezone.utc)
        await set_trade_status(db, trade, TradeStatus.FIAT_CONFIRMED, actor_user_id, "CLIENT", note="Seller confirmed fiat received")
        await P2PRiskService.apply(db, trade)

        # 🔐 Release crypto via escrow module
        buyer = await db.scalar(select(Users).where(Users.user_id == trade.buyer_id))
        user_tier = int(getattr(buyer, "kyc_tier", 0) or 0)

        fee = P2PFeeEngine.compute(
            token_amount=Decimal(trade.token_amount),
            price_bif_per_usd=Decimal(trade.price_bif_per_usd),
            risk_score=int(trade.risk_score or 0),
            user_tier=user_tier,
            token=str(trade.token.value),
        )
        fee_token = Decimal(fee["fee_token"])
        release_token = (Decimal(trade.token_amount) - fee_token).quantize(Decimal("0.00000001"))
        if release_token <= Decimal("0"):
            raise ValueError("Computed net release amount is not positive")

        # Release crypto net of fee
        await release_crypto_to_buyer(
            trade,
            release_token_amount=release_token,
            fee_token_amount=fee_token,
        )
        await ledger_release(db, trade, amount_token=release_token)
        if fee_token > Decimal("0"):
            await ledger_fee(
                db,
                trade,
                fee_token=fee_token,
                fee_bif=Decimal(fee["fee_bif"]),
                fee_rate=Decimal(fee["fee_rate"]),
            )
        await set_trade_status(db, trade, TradeStatus.RELEASED, actor_user_id, "SYSTEM", note="Crypto released to buyer")
        aml = await AMLEngine.evaluate_p2p(db, trade, event="P2P_RELEASE")
        trade.risk_score = aml["final_score"]
        trade.flags = sorted(set(list(trade.flags or []) + [h["code"] for h in aml["hits"]]))
        if aml["should_alert"]:
            await deliver_alerts(
                db,
                subject="AML Alert (P2P_RELEASE)",
                message=f"Trade {trade.trade_id} AML score {aml['final_score']}",
                metadata={
                    "trade_id": str(trade.trade_id),
                    "event": "P2P_RELEASE",
                    "hits": aml["hits"],
                },
            )
        inc("p2p.trade.released")

        await db.commit()
        await db.refresh(trade)
        return trade
