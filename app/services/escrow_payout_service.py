from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.escrow_order import EscrowOrder
from app.models.escrow_payout import EscrowPayout
from app.models.escrow_event import EscrowEvent
from app.models.escrow_enums import EscrowOrderStatus
from app.models.users import Users
from services.payout_port import PayoutProvider
from services.escrow_ledger_hooks import on_payout_confirmed
from app.services.circuit_breaker import (
    circuit_allow_payout,
    circuit_on_failure,
    circuit_on_success,
)
from app.services.liquidity_guard import LiquidityGuard
from app.services.aml_service import run_aml
from app.services.audit_service import audit_log
from app.services.risk_service import RiskService
from app.services.risk_decision_log import log_risk_decision
from app.services.aml_service import enqueue_alert
from app.services.payout.payout_router import PayoutRouter
from app.services.payout.providers.lumicash import LumicashProvider
from app.services.payout.providers.providerb import ProviderBProvider
from app.services.payout.providers.providerc import ProviderCProvider

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

        aml = await run_aml(
            db,
            user=user,
            order=order,
            stage="PAYOUT",
            actor_user_id=str(operator.user_id) if operator else None,
            actor_role=str(operator.role) if operator else "SYSTEM",
            ip=ip,
            user_agent=user_agent,
        )
        if aml.decision == "BLOCK":
            raise HTTPException(status_code=403, detail="AML blocked payout")
        if aml.decision == "REVIEW":
            order.flags = list(set(list(order.flags or []) + ["PAYOUT_REVIEW"]))
            await db.commit()
            return {"status": "PAYOUT_REVIEW"}

        ok, balance, needed = await LiquidityGuard.require_treasury(
            db,
            currency="BIF",
            required_amount=float(order.bif_target),
        )
        if not ok:
            order.flags = list(set(list(order.flags or []) + ["LIQUIDITY_PENDING"]))
            await audit_log(
                db,
                actor_user_id=str(operator.user_id) if operator else None,
                actor_role=str(operator.role) if operator else None,
                action="LIQUIDITY_BLOCK_PAYOUT",
                entity_type="escrow_order",
                entity_id=str(order.id),
                before_state=None,
                after_state={"balance": balance, "needed": needed, "currency": "BIF"},
                ip=ip,
                user_agent=user_agent,
            )
            await enqueue_alert(
                db,
                type="LIQUIDITY_LOW",
                severity="HIGH",
                user_id=str(order.user_id),
                order_id=str(order.id),
                payload={
                    "balance": balance,
                    "needed": needed,
                    "currency": "BIF",
                },
            )
            await db.commit()
            raise HTTPException(status_code=503, detail="Treasury liquidity insufficient")

        providers = [payout_port] if payout_port is not None else [
            LumicashProvider(),
            ProviderBProvider(),
            ProviderCProvider(),
        ]
        payout_router = PayoutRouter(providers)

        try:
            await db.execute(
                text(
                    """
                    UPDATE escrow.orders
                    SET payout_initiated_at = now()
                    WHERE id = :oid::uuid
                    """
                ),
                {"oid": str(order.id)},
            )

            routed = await payout_router.send_with_failover(
                db,
                amount_bif=float(order.bif_target),
                account_number=str(order.payout_account_number or ""),
                account_name=order.payout_account_name,
                reference=str(order.id),
            )

            await db.execute(
                text(
                    """
                    UPDATE escrow.orders
                    SET payout_provider = :p,
                        payout_reference = :ref
                    WHERE id = :oid::uuid
                    """
                ),
                {
                    "oid": str(order.id),
                    "p": str(routed.get("provider") or ""),
                    "ref": str(order.id),
                },
            )
            order.payout_provider = str(routed.get("provider") or order.payout_provider or "")
            order.payout_reference = str(order.id)
            order.payout_initiated_at = datetime.now(timezone.utc)
            order.paid_out_at = datetime.now(timezone.utc)
            order.flags = list(set(list(order.flags or []) + ["PAYOUT_SUCCESS"]))
        except Exception as exc:
            order.flags = list(set(list(order.flags or []) + ["PAYOUT_FAILED"]))
            await audit_log(
                db,
                actor_user_id=str(operator.user_id) if operator else None,
                actor_role=str(operator.role) if operator else None,
                action="ESCROW_PAYOUT_FAILED",
                entity_type="escrow_order",
                entity_id=str(order.id),
                before_state=None,
                after_state={"error": str(exc)},
                ip=ip,
                user_agent=user_agent,
            )
            await enqueue_alert(
                db,
                type="PAYOUT_PROVIDER_DOWN",
                severity="HIGH",
                user_id=str(order.user_id),
                order_id=str(order.id),
                payload={"error": str(exc)},
            )
            await db.commit()
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
        user = await db.get(Users, order.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        aml = await run_aml(
            db,
            user=user,
            order=order,
            stage="PAYOUT",
            actor_user_id=str(getattr(actor, "user_id", None) or getattr(actor, "id", None)) if actor else None,
            actor_role=str(getattr(actor, "role", "SYSTEM")) if actor else "SYSTEM",
            ip=request_ip,
            user_agent=request_ua,
        )
        if aml.decision == "BLOCK":
            flags = [str(f) for f in list(order.flags or [])]
            if "BLOCKED:AML_PAYOUT" not in flags:
                flags.append("BLOCKED:AML_PAYOUT")
            order.flags = flags
            raise HTTPException(status_code=403, detail=f"AML payout blocked: {aml.hits}")
        if aml.decision == "REVIEW":
            flags = [str(f) for f in list(order.flags or [])]
            if "MANUAL_REVIEW:AML_PAYOUT" not in flags:
                flags.append("MANUAL_REVIEW:AML_PAYOUT")
            order.flags = flags
            await db.commit()
            return {"status": "PAYOUT_REVIEW"}

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
