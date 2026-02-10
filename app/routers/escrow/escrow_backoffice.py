from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from models.escrow_order import EscrowOrder
from models.escrow_event import EscrowEvent
from models.escrow_proof import EscrowProof
from models.escrow_payout import EscrowPayout
from models.escrow_enums import EscrowOrderStatus, EscrowActorType, EscrowProofType
from schemas.escrow_backoffice import MarkPayoutPendingRequest, ConfirmPaidOutRequest
from services.escrow_ledger_hooks import on_payout_confirmed

# from auth import get_current_user
# from services.operator_guard import require_operator

router = APIRouter(prefix="/backoffice/escrow", tags=["Backoffice - Escrow"])

@router.get("/orders")
async def list_orders(status: str | None = None, db: AsyncSession = Depends(get_db)):
    try:
        q = select(EscrowOrder)
        if status:
            q = q.where(EscrowOrder.status == status)
        res = await db.execute(q.order_by(EscrowOrder.created_at.desc()).limit(100))
        orders = res.scalars().all()
        return [{"id": str(o.id), "status": o.status, "usdc_expected": str(o.usdc_expected), "bif_target": str(o.bif_target)} for o in orders]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/orders/{order_id}/payout-pending")
async def mark_payout_pending(order_id: str, body: MarkPayoutPendingRequest, db: AsyncSession = Depends(get_db)):
    try:
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
async def confirm_paid_out(order_id: str, body: ConfirmPaidOutRequest, db: AsyncSession = Depends(get_db)):
    try:
        res = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(404, "Order not found")
        if order.status != EscrowOrderStatus.PAYOUT_PENDING:
            raise HTTPException(400, f"Order must be PAYOUT_PENDING, current={order.status}")

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

        db.add(EscrowEvent(order_id=order.id, event_type="PAID_OUT_CONFIRMED", payload={"amount_bif": str(body.amount_bif)}))
        await db.commit()
        return {"status": "OK", "order_status": order.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
