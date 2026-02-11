from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from models.escrow_order import EscrowOrder
from models.escrow_enums import EscrowOrderStatus
from app.services.risk_service import RiskService
from app.services.risk_decision_log import log_risk_decision
from app.services.audit_service import audit_log

class EscrowService:

    @staticmethod
    async def create_order(
        db: AsyncSession,
        *,
        user,
        payload,
        ip: str | None,
        user_agent: str | None,
    ) -> EscrowOrder:
        if isinstance(payload, EscrowOrder):
            order = payload
            amount_usdc = float(order.usdc_expected or 0)
        else:
            if hasattr(payload, "model_dump"):
                payload_data = payload.model_dump(exclude_none=False)
            elif isinstance(payload, dict):
                payload_data = dict(payload)
            else:
                payload_data = dict(vars(payload))

            amount_usdc = float(
                payload_data.get("amount_usdc")
                or payload_data.get("usdc_expected")
                or 0
            )
            order = EscrowOrder(**payload_data)

        risk = await RiskService.evaluate_create_order(
            db,
            user=user,
            amount_usdc=amount_usdc,
            ip=ip,
        )
        await log_risk_decision(
            db,
            user_id=str(user.user_id),
            order_id=None,
            stage="CREATE",
            result=risk,
        )

        if risk.decision == "BLOCK":
            raise HTTPException(status_code=403, detail=f"Blocked: {risk.reasons}")

        order.risk_score = int(risk.score or 0)
        if risk.decision == "REVIEW":
            flags = [str(f) for f in list(order.flags or [])]
            if "MANUAL_REVIEW:CREATE" not in flags:
                flags.append("MANUAL_REVIEW:CREATE")
            order.flags = flags

        db.add(order)
        await db.flush()

        await audit_log(
            db,
            actor_user_id=str(user.user_id),
            actor_role=str(getattr(user, "role", "") or ""),
            action="ESCROW_CREATE",
            entity_type="escrow_order",
            entity_id=str(order.id),
            before_state=None,
            after_state={
                "status": str(order.status),
                "amount_usdc": amount_usdc,
                "risk": {
                    "score": risk.score,
                    "decision": risk.decision,
                    "reasons": risk.reasons,
                },
            },
            ip=ip,
            user_agent=user_agent,
        )
        return order

    @staticmethod
    async def get_order(db: AsyncSession, order_id: str) -> EscrowOrder:
        res = await db.execute(
            select(EscrowOrder).where(EscrowOrder.id == order_id)
        )
        order = res.scalar_one_or_none()
        if not order:
            raise ValueError("Escrow order not found")
        return order

    @staticmethod
    async def mark_funded(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.CREATED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.FUNDED
        await db.commit()

    @staticmethod
    async def mark_swapped(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.FUNDED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.SWAPPED
        await db.commit()

    @staticmethod
    async def mark_payout_pending(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.SWAPPED:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.PAYOUT_PENDING
        await db.commit()

    @staticmethod
    async def mark_paid_out(db: AsyncSession, order: EscrowOrder):
        if order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise ValueError("Invalid status transition")
        order.status = EscrowOrderStatus.PAID_OUT
        await db.commit()
