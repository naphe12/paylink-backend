from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escrow_enums import EscrowOrderStatus
from app.models.escrow_order import EscrowOrder
from app.services.audit import audit
from app.services.escrow_order_rules import transition_escrow_order_status
from app.services.escrow_tracking_ws import broadcast_tracking_update


class EscrowDisputeService:
    @staticmethod
    async def request_refund(
        db: AsyncSession,
        order: EscrowOrder,
        *,
        actor_user_id: str,
        actor_role: str,
        reason: str,
        reason_code: str | None = None,
        proof_type: str | None = None,
        proof_ref: str | None = None,
        step_up_method: str | None = None,
    ) -> EscrowOrder:
        previous_status = order.status
        transition_escrow_order_status(order, EscrowOrderStatus.REFUND_PENDING)
        order.updated_at = datetime.now(timezone.utc)

        await audit(
            db,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="ESCROW_REFUND_REQUESTED",
            metadata={
                "before": {"status": previous_status.value},
                "after": {
                    "status": order.status.value,
                    "reason": reason,
                    "reason_code": reason_code,
                    "proof_type": proof_type,
                    "proof_ref": proof_ref,
                    "step_up_method": step_up_method,
                },
            },
            entity_type="escrow_order",
            entity_id=str(order.id),
        )
        await db.commit()
        await broadcast_tracking_update(order)
        return order

    @staticmethod
    async def confirm_refund(
        db: AsyncSession,
        order: EscrowOrder,
        *,
        actor_user_id: str,
        actor_role: str,
        resolution: str,
        resolution_code: str | None = None,
        proof_type: str | None = None,
        proof_ref: str | None = None,
        step_up_method: str | None = None,
    ) -> EscrowOrder:
        previous_status = order.status
        transition_escrow_order_status(order, EscrowOrderStatus.REFUNDED)
        order.updated_at = datetime.now(timezone.utc)

        await audit(
            db,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="ESCROW_REFUNDED",
            metadata={
                "before": {"status": previous_status.value},
                "after": {
                    "status": order.status.value,
                    "resolution": resolution,
                    "resolution_code": resolution_code,
                    "proof_type": proof_type,
                    "proof_ref": proof_ref,
                    "step_up_method": step_up_method,
                },
            },
            entity_type="escrow_order",
            entity_id=str(order.id),
        )
        await db.commit()
        await broadcast_tracking_update(order)
        return order
