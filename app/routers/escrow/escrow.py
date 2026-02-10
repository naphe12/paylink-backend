from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from models.escrow_order import EscrowOrder
from services.escrow_service import EscrowService
from app.core.database import get_db
import math

from models.escrow_enums import EscrowOrderStatus

router = APIRouter(prefix="/escrow", tags=["Escrow"])
DAILY_USDC_LIMIT = 5000
DAILY_TX_LIMIT = 20
MAX_OPEN_CREATED_ORDERS = 5


def _estimate_minutes_remaining(order: EscrowOrder) -> int:
    status = order.status.value if hasattr(order.status, "value") else str(order.status)
    terminal_statuses = {"PAID_OUT", "CANCELLED", "EXPIRED", "REFUNDED", "FAILED"}
    if status in terminal_statuses:
        return 0

    network = (
        order.deposit_network.value
        if hasattr(order.deposit_network, "value")
        else str(order.deposit_network or "POLYGON")
    ).upper()
    minutes_per_confirmation = {
        "POLYGON": 0.5,
        "ETHEREUM": 1.0,
        "ARBITRUM": 0.3,
        "OPTIMISM": 0.3,
        "BSC": 0.5,
        "SOLANA": 0.2,
        "TRON": 0.5,
    }.get(network, 1.0)

    current_confirmations = int(order.deposit_confirmations or 0)
    required_confirmations = int(order.deposit_required_confirmations or 0)
    remaining_confirmations = max(required_confirmations - current_confirmations, 0)
    confirmations_minutes = math.ceil(remaining_confirmations * minutes_per_confirmation)

    if status == EscrowOrderStatus.CREATED.value:
        return confirmations_minutes + 8
    if status == EscrowOrderStatus.FUNDED.value:
        return 6
    if status == EscrowOrderStatus.SWAPPED.value:
        return 4
    if status == EscrowOrderStatus.PAYOUT_PENDING.value:
        return 2
    return confirmations_minutes

@router.post("/orders", response_model=dict)
async def create_escrow(
    order_payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        order = EscrowOrder(**order_payload)
        today_stats = (
            await db.execute(
                text(
                    """
                    SELECT
                      COALESCE(SUM(usdc_expected), 0) AS total_usdc_today,
                      COUNT(*) AS tx_count_today,
                      COALESCE(SUM(CASE WHEN status = 'CREATED' THEN 1 ELSE 0 END), 0) AS open_created_count
                    FROM escrow.orders
                    WHERE user_id = :user_id
                      AND created_at >= date_trunc('day', now())
                    """
                ),
                {"user_id": str(order.user_id)},
            )
        ).first()
        total_usdc_today = float(today_stats[0] or 0)
        tx_count_today = int(today_stats[1] or 0)
        open_created_count = int(today_stats[2] or 0)
        incoming_usdc = float(order.usdc_expected or 0)

        if total_usdc_today + incoming_usdc > DAILY_USDC_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Limite quotidienne atteinte. Veuillez reessayer demain.",
            )
        if tx_count_today >= DAILY_TX_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Nombre maximum de transactions quotidiennes atteint.",
            )
        if open_created_count >= MAX_OPEN_CREATED_ORDERS:
            raise HTTPException(
                status_code=429,
                detail="Trop d'ordres en attente. Finalisez un ordre avant de continuer.",
            )

        is_sandbox = request.headers.get("X-SANDBOX", "false").lower() == "true"
        sandbox_scenario = (request.headers.get("X-SANDBOX-SCENARIO") or "").strip().upper()
        if is_sandbox:
            flags = list(order.flags or [])
            if "SANDBOX" not in flags:
                flags.append("SANDBOX")
            if sandbox_scenario:
                flags = [f for f in flags if not str(f).startswith("SANDBOX_SCENARIO:")]
                flags.append(f"SANDBOX_SCENARIO:{sandbox_scenario}")
            order.flags = flags
            if sandbox_scenario == "CONFIRMATION_DELAY":
                order.status = EscrowOrderStatus.CREATED
                order.usdc_received = 0
                order.deposit_confirmations = 0
            elif sandbox_scenario == "SWAP_FAILED":
                order.status = EscrowOrderStatus.FAILED
                order.usdc_received = order.usdc_expected
                order.deposit_confirmations = order.deposit_required_confirmations
                order.funded_at = datetime.now(timezone.utc)
            elif sandbox_scenario == "PAYOUT_BLOCKED":
                order.status = EscrowOrderStatus.PAYOUT_PENDING
                order.usdc_received = order.usdc_expected
                order.deposit_confirmations = order.deposit_required_confirmations
                order.funded_at = datetime.now(timezone.utc)
            elif sandbox_scenario == "WEBHOOK_FAILED":
                order.status = EscrowOrderStatus.CREATED
                order.usdc_received = 0
                order.deposit_confirmations = 0
            else:
                order.status = EscrowOrderStatus.FUNDED
                order.usdc_received = order.usdc_expected
                order.deposit_confirmations = order.deposit_required_confirmations
                order.funded_at = datetime.now(timezone.utc)

        o = await EscrowService.create_order(db, order)
        return {
            "id": str(o.id),
            "status": o.status,
            "is_sandbox": "SANDBOX" in list(o.flags or []),
            "sandbox_scenario": next(
                (str(f).split(":", 1)[1] for f in list(o.flags or []) if str(f).startswith("SANDBOX_SCENARIO:")),
                None,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders/{order_id}", response_model=dict)
async def get_escrow(order_id: str, db: AsyncSession = Depends(get_db)):
    try:
        o = await EscrowService.get_order(db, order_id)
        return {
            "id": str(o.id),
            "status": o.status,
            "is_sandbox": "SANDBOX" in list(o.flags or []),
            "sandbox_scenario": next(
                (str(f).split(":", 1)[1] for f in list(o.flags or []) if str(f).startswith("SANDBOX_SCENARIO:")),
                None,
            ),
            "network": o.deposit_network,
            "amount_usdc": o.usdc_expected,
            "usdc_expected": o.usdc_expected,
            "usdc_received": o.usdc_received,
            "bif_target": o.bif_target,
            "recipient_name": o.payout_account_name,
            "recipient_phone": o.payout_account_number,
            "deposit_address": o.deposit_address,
            "confirmations": o.deposit_confirmations,
            "required_confirmations": o.deposit_required_confirmations,
            "tx_hash": o.deposit_tx_hash,
            "estimated_minutes_remaining": _estimate_minutes_remaining(o),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/orders/{order_id}/mark-paid")
async def mark_paid(order_id: str, db: AsyncSession = Depends(get_db)):
    try:
        o = await EscrowService.get_order(db, order_id)
        await EscrowService.mark_paid_out(db, o)
        return {"status": "PAID_OUT"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/retry", response_model=dict)
async def retry_order_payment(order_id: str, db: AsyncSession = Depends(get_db)):
    try:
        o = await EscrowService.get_order(db, order_id)
        current_status = o.status.value if hasattr(o.status, "value") else str(o.status)
        can_retry = current_status in {"CREATED", "FUNDED"}
        if not can_retry:
            raise HTTPException(status_code=400, detail=f"Retry not allowed for status={current_status}")

        await db.execute(
            text(
                """
                ALTER TABLE escrow.orders
                ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0
                """
            )
        )
        await db.execute(
            text(
                """
                UPDATE escrow.orders
                SET retry_count = COALESCE(retry_count, 0) + 1,
                    expires_at = now() + interval '30 minutes',
                    updated_at = now()
                WHERE id = :order_id
                """
            ),
            {"order_id": str(o.id)},
        )
        await db.execute(
            text(
                """
                INSERT INTO escrow.events (order_id, event_type, payload)
                VALUES (:order_id, :event_type, CAST(:payload AS jsonb))
                """
            ),
            {
                "order_id": str(o.id),
                "event_type": "PAYMENT_RETRY_REQUESTED",
                "payload": '{"source":"client"}',
            },
        )
        await db.commit()

        refreshed = await EscrowService.get_order(db, order_id)
        return {
            "status": "OK",
            "order_id": str(refreshed.id),
            "escrow_status": refreshed.status,
            "expires_at": refreshed.expires_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
