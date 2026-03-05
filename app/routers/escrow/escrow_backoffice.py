from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
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
from app.services.escrow_tracking_ws import broadcast_tracking_update
from schemas.escrow_backoffice import MarkPayoutPendingRequest, ConfirmPaidOutRequest
from services.escrow_ledger_hooks import on_payout_confirmed

# from auth import get_current_user
# from services.operator_guard import require_operator

router = APIRouter(prefix="/backoffice/escrow", tags=["Backoffice - Escrow"])


def _require_backoffice_role(user: Users) -> None:
    role = str(getattr(user, "role", "")).lower()
    if role not in {"admin", "agent", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve au backoffice")


def _order_row_to_dict(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "status": r["status"],
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "user_name": r.get("user_name"),
        "trader_id": str(r["trader_id"]) if r["trader_id"] else None,
        "trader_name": r.get("trader_name"),
        "usdc_expected": float(r["usdc_expected"]) if r["usdc_expected"] is not None else None,
        "usdc_received": float(r["usdc_received"]) if r["usdc_received"] is not None else None,
        "usdt_target": float(r["usdt_target"]) if r["usdt_target"] is not None else None,
        "usdt_received": float(r["usdt_received"]) if r["usdt_received"] is not None else None,
        "bif_target": float(r["bif_target"]) if r["bif_target"] is not None else None,
        "bif_paid": float(r["bif_paid"]) if r["bif_paid"] is not None else None,
        "risk_score": int(r["risk_score"]) if r["risk_score"] is not None else 0,
        "flags": list(r.get("flags") or []),
        "deposit_network": r.get("deposit_network"),
        "deposit_address": r.get("deposit_address"),
        "deposit_tx_hash": r.get("deposit_tx_hash"),
        "payout_method": r.get("payout_method"),
        "payout_provider": r.get("payout_provider"),
        "payout_account_name": r.get("payout_account_name"),
        "payout_account_number": r.get("payout_account_number"),
        "payout_reference": r.get("payout_reference"),
        "funded_at": r.get("funded_at"),
        "swapped_at": r.get("swapped_at"),
        "payout_initiated_at": r.get("payout_initiated_at"),
        "paid_out_at": r.get("paid_out_at"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }

@router.get("/orders")
async def list_orders(
    status: str | None = None,
    min_risk: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_backoffice_role(user)
    status_filter = None if str(status or "").upper() in {"", "ALL"} else str(status).upper()
    try:
        rows = await db.execute(
            text(
                """
                SELECT
                  o.id,
                  o.status::text AS status,
                  o.user_id,
                  u.full_name AS user_name,
                  o.trader_id,
                  t.full_name AS trader_name,
                  o.usdc_expected,
                  o.usdc_received,
                  o.usdt_target,
                  o.usdt_received,
                  o.bif_target,
                  o.bif_paid,
                  o.risk_score,
                  o.flags,
                  o.deposit_network,
                  o.deposit_address,
                  o.deposit_tx_hash,
                  o.payout_method::text AS payout_method,
                  o.payout_provider,
                  o.payout_account_name,
                  o.payout_account_number,
                  o.payout_reference,
                  o.funded_at,
                  o.swapped_at,
                  o.payout_initiated_at,
                  o.paid_out_at,
                  o.created_at,
                  o.updated_at
                FROM escrow.orders o
                LEFT JOIN paylink.users u ON u.user_id = o.user_id
                LEFT JOIN paylink.users t ON t.user_id = o.trader_id
                WHERE (:status IS NULL OR o.status::text = :status)
                  AND (:min_risk IS NULL OR COALESCE(o.risk_score, 0) >= :min_risk)
                  AND (:created_from IS NULL OR o.created_at >= :created_from)
                  AND (:created_to IS NULL OR o.created_at <= :created_to)
                ORDER BY o.created_at DESC
                LIMIT 200
                """
            ),
            {
                "status": status_filter,
                "min_risk": min_risk,
                "created_from": created_from,
                "created_to": created_to,
            },
        )
        return [_order_row_to_dict(r) for r in rows.mappings().all()]
    except Exception:
        # Fallback for environments where schema/column types differ.
        q = select(EscrowOrder)
        if status_filter:
            q = q.where(EscrowOrder.status == status_filter)
        if min_risk is not None:
            q = q.where(EscrowOrder.risk_score >= min_risk)
        if created_from is not None:
            q = q.where(EscrowOrder.created_at >= created_from)
        if created_to is not None:
            q = q.where(EscrowOrder.created_at <= created_to)
        res = await db.execute(q.order_by(EscrowOrder.created_at.desc()).limit(200))
        orders = res.scalars().all()
        return [
            {
                "id": str(o.id),
                "status": str(o.status),
                "user_id": str(o.user_id) if o.user_id else None,
                "user_name": None,
                "trader_id": str(o.trader_id) if o.trader_id else None,
                "trader_name": None,
                "usdc_expected": float(o.usdc_expected) if o.usdc_expected is not None else None,
                "usdc_received": float(o.usdc_received) if o.usdc_received is not None else None,
                "usdt_target": float(o.usdt_target) if o.usdt_target is not None else None,
                "usdt_received": float(o.usdt_received) if o.usdt_received is not None else None,
                "bif_target": float(o.bif_target) if o.bif_target is not None else None,
                "bif_paid": float(o.bif_paid) if o.bif_paid is not None else None,
                "risk_score": int(o.risk_score or 0),
                "flags": list(o.flags or []),
                "deposit_network": str(o.deposit_network) if o.deposit_network else None,
                "deposit_address": o.deposit_address,
                "deposit_tx_hash": o.deposit_tx_hash,
                "payout_method": str(o.payout_method) if o.payout_method else None,
                "payout_provider": o.payout_provider,
                "payout_account_name": o.payout_account_name,
                "payout_account_number": o.payout_account_number,
                "payout_reference": o.payout_reference,
                "funded_at": o.funded_at,
                "swapped_at": o.swapped_at,
                "payout_initiated_at": o.payout_initiated_at,
                "paid_out_at": o.paid_out_at,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in orders
        ]

@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_backoffice_role(user)
    try:
        row = await db.execute(
            text(
                """
                SELECT
                  o.id,
                  o.status::text AS status,
                  o.user_id,
                  u.full_name AS user_name,
                  o.trader_id,
                  t.full_name AS trader_name,
                  o.usdc_expected,
                  o.usdc_received,
                  o.usdt_target,
                  o.usdt_received,
                  o.bif_target,
                  o.bif_paid,
                  o.risk_score,
                  o.flags,
                  o.deposit_network,
                  o.deposit_address,
                  o.deposit_tx_hash,
                  o.payout_method::text AS payout_method,
                  o.payout_provider,
                  o.payout_account_name,
                  o.payout_account_number,
                  o.payout_reference,
                  o.funded_at,
                  o.swapped_at,
                  o.payout_initiated_at,
                  o.paid_out_at,
                  o.created_at,
                  o.updated_at
                FROM escrow.orders o
                LEFT JOIN paylink.users u ON u.user_id = o.user_id
                LEFT JOIN paylink.users t ON t.user_id = o.trader_id
                WHERE o.id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": order_id},
        )
        mapped = row.mappings().first()
        if not mapped:
            raise HTTPException(status_code=404, detail="Order not found")
        return _order_row_to_dict(mapped)
    except HTTPException:
        raise
    except Exception:
        result = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
        o = result.scalar_one_or_none()
        if not o:
            raise HTTPException(status_code=404, detail="Order not found")
        return {
            "id": str(o.id),
            "status": str(o.status),
            "user_id": str(o.user_id) if o.user_id else None,
            "user_name": None,
            "trader_id": str(o.trader_id) if o.trader_id else None,
            "trader_name": None,
            "usdc_expected": float(o.usdc_expected) if o.usdc_expected is not None else None,
            "usdc_received": float(o.usdc_received) if o.usdc_received is not None else None,
            "usdt_target": float(o.usdt_target) if o.usdt_target is not None else None,
            "usdt_received": float(o.usdt_received) if o.usdt_received is not None else None,
            "bif_target": float(o.bif_target) if o.bif_target is not None else None,
            "bif_paid": float(o.bif_paid) if o.bif_paid is not None else None,
            "risk_score": int(o.risk_score or 0),
            "flags": list(o.flags or []),
            "deposit_network": str(o.deposit_network) if o.deposit_network else None,
            "deposit_address": o.deposit_address,
            "deposit_tx_hash": o.deposit_tx_hash,
            "payout_method": str(o.payout_method) if o.payout_method else None,
            "payout_provider": o.payout_provider,
            "payout_account_name": o.payout_account_name,
            "payout_account_number": o.payout_account_number,
            "payout_reference": o.payout_reference,
            "funded_at": o.funded_at,
            "swapped_at": o.swapped_at,
            "payout_initiated_at": o.payout_initiated_at,
            "paid_out_at": o.paid_out_at,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
        }

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
        await broadcast_tracking_update(order)
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
            metadata_=body.proof_metadata,
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
        await broadcast_tracking_update(order)
        return {"status": "OK", "order_status": order.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
