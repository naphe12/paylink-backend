from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.p2p_dispute import P2PDispute
from app.models.p2p_trade import P2PTrade
from app.models.p2p_enums import TradeStatus, DisputeStatus
from app.services.audit import audit
from app.services.p2p_release_service import release_crypto_to_buyer
from app.services.p2p_trade_state import set_trade_status

class P2PDisputeService:
    @staticmethod
    async def open_dispute(
        db: AsyncSession,
        trade_id,
        opened_by,
        reason: str,
        reason_code: str | None = None,
        proof_type: str | None = None,
        proof_ref: str | None = None,
    ) -> P2PDispute:
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise ValueError("Trade not found")

        if opened_by not in (trade.buyer_id, trade.seller_id):
            raise PermissionError("Not a party of this trade")

        dispute = P2PDispute(trade_id=trade.trade_id, opened_by=opened_by, reason=reason, status=DisputeStatus.OPEN)
        db.add(dispute)
        await set_trade_status(db, trade, TradeStatus.DISPUTED, opened_by, "CLIENT", note="Dispute opened")
        await audit(
            db,
            actor_user_id=str(opened_by),
            actor_role="CLIENT",
            action="P2P_DISPUTE_OPENED",
            metadata={
                "after": {
                    "trade_id": str(trade.trade_id),
                    "trade_status": TradeStatus.DISPUTED.value,
                    "dispute_status": DisputeStatus.OPEN.value,
                    "reason": reason,
                    "reason_code": reason_code,
                    "proof_type": proof_type,
                    "proof_ref": proof_ref,
                },
            },
            entity_type="p2p_trade",
            entity_id=str(trade.trade_id),
        )

        await db.commit()
        await db.refresh(dispute)
        return dispute

    @staticmethod
    async def resolve_dispute(
        db: AsyncSession,
        trade_id,
        resolved_by,
        outcome: str,
        resolution: str,
        resolution_code: str | None = None,
        proof_type: str | None = None,
        proof_ref: str | None = None,
        step_up_method: str | None = None,
    ) -> P2PDispute:
        trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
        if not trade:
            raise ValueError("Trade not found")
        if trade.status != TradeStatus.DISPUTED:
            raise ValueError("Trade not in DISPUTED")

        dispute = await db.scalar(
            select(P2PDispute)
            .where(
                P2PDispute.trade_id == trade_id,
                P2PDispute.status.in_([DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]),
            )
        )
        if not dispute:
            raise ValueError("Open dispute not found")

        previous_dispute_status = dispute.status
        dispute.resolution = resolution
        dispute.resolved_by = resolved_by
        dispute.resolved_at = datetime.now(timezone.utc)

        await set_trade_status(
            db,
            trade,
            TradeStatus.RESOLVED,
            resolved_by,
            "ADMIN",
            note=f"Dispute resolved: {outcome}",
        )

        if outcome == "buyer_wins":
            dispute.status = DisputeStatus.RESOLVED_BUYER
            await release_crypto_to_buyer(trade)
            await set_trade_status(
                db,
                trade,
                TradeStatus.RELEASED,
                resolved_by,
                "ADMIN",
                note="Admin released crypto to buyer after dispute",
            )
        elif outcome == "seller_wins":
            dispute.status = DisputeStatus.RESOLVED_SELLER
            await set_trade_status(
                db,
                trade,
                TradeStatus.CANCELLED,
                resolved_by,
                "ADMIN",
                note="Admin cancelled trade in favor of seller after dispute",
            )
        else:
            raise ValueError("Unsupported dispute outcome")

        await audit(
            db,
            actor_user_id=str(resolved_by),
            actor_role="ADMIN",
            action="P2P_DISPUTE_RESOLVED",
            metadata={
                "before": {
                    "trade_status": TradeStatus.DISPUTED.value,
                    "dispute_status": previous_dispute_status.value,
                },
                "after": {
                    "trade_id": str(trade.trade_id),
                    "trade_status": trade.status.value,
                    "dispute_status": dispute.status.value,
                    "outcome": outcome,
                    "resolution": resolution,
                    "resolution_code": resolution_code,
                    "proof_type": proof_type,
                    "proof_ref": proof_ref,
                    "step_up_method": step_up_method,
                },
            },
            entity_type="p2p_dispute",
            entity_id=str(dispute.dispute_id),
        )

        await db.commit()
        await db.refresh(dispute)
        return dispute
