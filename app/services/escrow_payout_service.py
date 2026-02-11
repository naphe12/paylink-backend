from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.escrow_order import EscrowOrder
from models.escrow_payout import EscrowPayout
from models.escrow_event import EscrowEvent
from models.escrow_enums import EscrowOrderStatus
from app.models.users import Users
from services.payout_port import PayoutProvider
from services.escrow_ledger_hooks import on_payout_confirmed
from app.services.circuit_breaker import (
    circuit_allow_payout,
    circuit_on_failure,
    circuit_on_success,
)
from app.services.audit_service import audit_log
from app.services.risk_service import RiskService
from app.services.risk_decision_log import log_risk_decision

class EscrowPayoutService:
    @staticmethod
    async def confirm_payout(
        db: AsyncSession,
        *,
        order,
        operator,
        ip: str | None,
        user_agent: str | None,
        payout_port: PayoutProvider | None = None,
    ):
        if order.status != EscrowOrderStatus.SWAPPED:
            raise HTTPException(status_code=400, detail="Order not ready for payout")

        user = await db.get(Users, order.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        risk = await RiskService.evaluate_payout(
            db,
            user=user,
            order=order,
        )
        await log_risk_decision(
            db,
            user_id=str(user.user_id),
            order_id=str(order.id),
            stage="PAYOUT",
            result=risk,
        )

        if risk.decision == "BLOCK":
            raise HTTPException(status_code=403, detail=f"Payout blocked: {risk.reasons}")

        if risk.decision == "REVIEW":
            flags = [str(f) for f in list(order.flags or [])]
            if "MANUAL_REVIEW:PAYOUT" not in flags:
                flags.append("MANUAL_REVIEW:PAYOUT")
            order.flags = flags
            return {"status": "PAYOUT_REVIEW"}

        if payout_port is not None:
            if not await circuit_allow_payout(db):
                raise HTTPException(status_code=503, detail="Payout temporarily disabled (circuit breaker)")
            try:
                payout_result = await payout_port.send_bif(
                    float(order.bif_target),
                    {
                        "provider": order.payout_provider,
                        "account": order.payout_account_number,
                        "name": order.payout_account_name,
                    },
                )
                order.payout_reference = getattr(payout_result, "reference", None) or order.payout_reference
                await circuit_on_success(db)
            except Exception:
                await circuit_on_failure(db)
                raise

        before_state = {"status": str(order.status)}
        order.bif_paid = order.bif_target
        order.paid_out_at = datetime.now(timezone.utc)
        await on_payout_confirmed(db, order)
        order.status = EscrowOrderStatus.PAID_OUT

        await audit_log(
            db,
            actor_user_id=str(operator.user_id),
            actor_role=str(operator.role),
            action="ESCROW_PAYOUT_CONFIRMED",
            entity_type="escrow_order",
            entity_id=str(order.id),
            before_state=before_state,
            after_state={"status": "PAID_OUT"},
            ip=ip,
            user_agent=user_agent,
        )

        return {"status": "PAID_OUT"}

    def __init__(self, provider: PayoutProvider):
        self.provider = provider

    async def execute_payout(
        self,
        db: AsyncSession,
        order_id: str,
        *,
        actor=None,
        request_ip: str | None = None,
        request_ua: str | None = None,
    ):
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order or order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise ValueError("Order not ready for payout")
        before = {"status": str(order.status), "bif_paid": str(order.bif_paid)}

        if not await circuit_allow_payout(db):
            raise HTTPException(status_code=503, detail="Payout temporarily disabled (circuit breaker)")
        try:
            result = await self.provider.send_bif(
                float(order.bif_target),
                {
                    "provider": order.payout_provider,
                    "account": order.payout_account_number,
                    "name": order.payout_account_name,
                }
            )
            await circuit_on_success(db)
        except Exception:
            await circuit_on_failure(db)
            raise

        payout = EscrowPayout(
            order_id=order.id,
            method=order.payout_method,
            provider=order.payout_provider,
            account_name=order.payout_account_name,
            account_number=order.payout_account_number,
            amount_bif=order.bif_target,
            reference=result.reference,
            status="CONFIRMED",
            initiated_at=order.payout_initiated_at or datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(payout)

        order.bif_paid = order.bif_target
        order.paid_out_at = datetime.now(timezone.utc)
        order.status = EscrowOrderStatus.PAID_OUT

        db.add(EscrowEvent(
            order_id=order.id,
            event_type="AUTO_PAYOUT_CONFIRMED",
            payload={"reference": result.reference},
        ))

        after = {"status": str(order.status), "bif_paid": str(order.bif_paid)}
        actor_id = getattr(actor, "id", None) or getattr(actor, "user_id", None)
        actor_role = getattr(actor, "role", None) or "SYSTEM"
        await audit_log(
            db,
            actor_user_id=str(actor_id) if actor_id else None,
            actor_role=str(actor_role) if actor_role else None,
            action="ESCROW_PAYOUT_CONFIRMED",
            entity_type="escrow_order",
            entity_id=str(order.id),
            before_state=before,
            after_state=after,
            ip=request_ip,
            user_agent=request_ua,
        )
        await db.commit()
