from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.services.audit_service import audit_log
from app.services.risk_decision_log import log_risk_decision
from app.services.risk_service import RiskService
from app.models.escrow_order import EscrowOrder
from app.models.escrow_event import EscrowEvent
from app.models.escrow_proof import EscrowProof
from app.models.escrow_payout import EscrowPayout
from app.models.escrow_enums import EscrowOrderStatus, EscrowActorType, EscrowProofType
from schemas.escrow_backoffice import MarkPayoutPendingRequest, ConfirmPaidOutRequest
from services.escrow_ledger_hooks import on_payout_confirmed

# from auth import get_current_user
# from services.operator_guard import require_operator

router = APIRouter(prefix="/backoffice/escrow", tags=["Backoffice - Escrow"])


def _require_backoffice_role(user: Users) -> None:
    role = str(getattr(user, "role", "")).lower()
    if role not in {"admin", "agent", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve au backoffice")

@router.get("/orders")
async def list_orders(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    try:
        _require_backoffice_role(user)
        q = select(EscrowOrder)
        if status:
            q = q.where(EscrowOrder.status == status)
        res = await db.execute(q.order_by(EscrowOrder.created_at.desc()).limit(100))
        orders = res.scalars().all()
        return [{"id": str(o.id), "status": o.status, "usdc_expected": str(o.usdc_expected), "bif_target": str(o.bif_target)} for o in orders]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/orders/{order_id}/payout-pending")
async def mark_payout_pending(
    order_id: str,
    body: MarkPayoutPendingRequest,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    try:
        _require_backoffice_role(user)
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(404, "Order not found")
        if order.status != EscrowOrderStatus.SWAPPED:
            raise HTTPException(400, f"Order must be SWAPPED, current={order.status}")

        order.status = EscrowOrderStatus.PAYOUT_PENDING
        order.payout_initiated_at = datetime.now(timezone.utc)
        if body.payout_reference:
            order.payout_reference = body.payout_reference

        db.add(EscrowEvent(order_id=order.id, event_type="PAYOUT_PENDING_SET", payload={"ref": body.payout_reference}))
        await db.commit()
        return {"status": "OK", "order_status": order.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/orders/{order_id}/paid-out")
async def confirm_paid_out(
    order_id: str,
    body: ConfirmPaidOutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    try:
        _require_backoffice_role(user)
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(404, "Order not found")
        if order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise HTTPException(400, f"Order must be PAYOUT_PENDING, current={order.status}")
        before = {"status": str(order.status), "bif_paid": float(order.bif_paid or 0)}

        owner = await db.scalar(select(Users).where(Users.user_id == order.user_id))
        if owner:
            risk = await RiskService.evaluate_payout(db, user=owner, order=order)
            await log_risk_decision(
                db,
                user_id=str(owner.user_id),
                order_id=str(order.id),
                stage="PAYOUT",
                result=risk,
            )
            if risk.decision == "BLOCK":
                await db.commit()
                raise HTTPException(status_code=403, detail=f"Payout blocked: {risk.reasons}")
            if risk.decision == "REVIEW":
                flags = [str(f) for f in list(order.flags or [])]
                if "MANUAL_REVIEW:PAYOUT" not in flags:
                    flags.append("MANUAL_REVIEW:PAYOUT")
                order.flags = flags
                await db.commit()
                return {"status": "PAYOUT_REVIEW", "reasons": risk.reasons}

        # Record payout row
        payout = EscrowPayout(
            order_id=order.id,
            method=order.payout_method,
            provider=order.payout_provider,
            account_name=order.payout_account_name,
            account_number=order.payout_account_number,
            amount_bif=body.amount_bif,
            reference=body.payout_reference,
            status="CONFIRMED",
            initiated_at=order.payout_initiated_at or datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(payout)

        # Record proof
        proof = EscrowProof(
            order_id=order.id,
            proof_type=EscrowProofType(body.proof_type),
            proof_ref=body.proof_ref,
            metadata=body.proof_metadata,
            created_by_type=EscrowActorType.OPERATOR,
        )
        db.add(proof)

        # Update order aggregate
        order.bif_paid = body.amount_bif
        order.payout_reference = body.payout_reference
        order.paid_out_at = datetime.now(timezone.utc)
        order.status = EscrowOrderStatus.PAID_OUT
        await on_payout_confirmed(db, order)
        after = {"status": "PAID_OUT", "bif_paid": float(order.bif_paid or 0)}
        actor_id = getattr(user, "id", None) or getattr(user, "user_id", None)
        await audit_log(
            db,
            actor_user_id=str(actor_id) if actor_id else None,
            actor_role=str(getattr(user, "role", "") or ""),
            action="ESCROW_PAYOUT_CONFIRMED",
            entity_type="escrow_order",
            entity_id=str(order.id),
            before_state=before,
            after_state=after,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        db.add(EscrowEvent(order_id=order.id, event_type="PAID_OUT_CONFIRMED", payload={"amount_bif": str(body.amount_bif)}))
        await db.commit()
        return {"status": "OK", "order_status": order.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
