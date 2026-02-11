from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from models.escrow_order import EscrowOrder
from services.escrow_service import EscrowService
from app.core.database import get_db
from app.config import settings
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.security.rate_limit import rate_limit
from app.services.audit_service import audit_log
from app.services.risk_decision_log import log_risk_decision
from app.services.risk_service import RiskService
import math

from models.escrow_enums import EscrowOrderStatus
from services.escrow_ledger_hooks import (
    post_funded_usdc_deposit_journal,
    post_swap_usdc_to_usdt_journal,
    on_payout_confirmed,
)

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
    current_user: Users = Depends(get_current_user_db),
):
    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        user_id = str(getattr(current_user, "user_id", ""))

        await rate_limit(request, key=f"user:{user_id}:escrow_create_min", limit=5, window_seconds=60)
        await rate_limit(request, key=f"user:{user_id}:escrow_create_hour", limit=20, window_seconds=3600)

        user_status = str(getattr(current_user, "status", "")).lower()
        user_kyc = str(getattr(current_user, "kyc_status", "")).lower()
        if user_status != "active":
            raise HTTPException(status_code=403, detail="Compte inactif pour creation escrow")
        if user_kyc != "verified":
            raise HTTPException(status_code=403, detail="KYC non verifie")
        if bool(getattr(current_user, "external_transfers_blocked", False)):
            raise HTTPException(status_code=403, detail="Transferts externes bloques")

        if "amount_usdc" in order_payload:
            raw_amount = order_payload.get("amount_usdc")
            try:
                amount_usdc = Decimal(str(raw_amount))
            except (InvalidOperation, TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Montant USDC invalide")

            if amount_usdc <= 0:
                raise HTTPException(status_code=400, detail="Le montant USDC doit etre superieur a 0")

            rate_bif_usdt = Decimal(str(order_payload.get("rate_bif_usdt", "2900")))
            payout_name = str(order_payload.get("recipient_name") or "").strip()
            payout_phone = str(order_payload.get("recipient_phone") or "").strip()
            if not payout_name or not payout_phone:
                raise HTTPException(status_code=400, detail="Nom et telephone du beneficiaire sont obligatoires")

            user_uuid = current_user.user_id

            synthetic_address = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
            order_payload = {
                "user_id": user_uuid,
                "usdc_expected": amount_usdc,
                "usdt_target": amount_usdc,
                "conversion_rate_usdc_usdt": Decimal("1"),
                "rate_bif_usdt": rate_bif_usdt,
                "bif_target": (amount_usdc * rate_bif_usdt).quantize(Decimal("0.01")),
                "deposit_network": order_payload.get("deposit_network", "POLYGON"),
                "deposit_address": order_payload.get("deposit_address") or synthetic_address,
                "deposit_required_confirmations": int(order_payload.get("deposit_required_confirmations", 1)),
                "deposit_tx_amount": Decimal("0"),
                "payout_account_name": payout_name,
                "payout_account_number": payout_phone,
                "payout_method": order_payload.get("payout_method", "MOBILE_MONEY"),
                "flags": list(order_payload.get("flags") or []),
            }

        order = EscrowOrder(**order_payload)
        incoming_usdc = float(order.usdc_expected or 0)

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

        o = await EscrowService.create_order(
            db,
            user=current_user,
            payload=order,
            ip=ip,
            user_agent=ua,
        )
        await db.commit()
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
async def get_escrow(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        o = await EscrowService.get_order(db, order_id)
        current_user_id = str(getattr(current_user, "user_id", ""))
        current_role = str(getattr(current_user, "role", "")).lower()
        is_owner = str(o.user_id) == current_user_id
        if not is_owner and current_role not in {"admin", "agent", "operator"}:
            raise HTTPException(status_code=403, detail="Acces refuse")
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
async def mark_paid(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        current_role = str(getattr(current_user, "role", "")).lower()
        if current_role not in {"admin", "operator"}:
            raise HTTPException(status_code=403, detail="Acces reserve aux operateurs")
        o = await EscrowService.get_order(db, order_id)
        before = {"status": str(o.status), "bif_paid": float(o.bif_paid or 0)}
        owner = await db.get(Users, o.user_id)
        if owner:
            risk = await RiskService.evaluate_payout(db, user=owner, order=o)
            await log_risk_decision(
                db,
                user_id=str(owner.user_id),
                order_id=str(o.id),
                stage="PAYOUT",
                result=risk,
            )
            if risk.decision == "BLOCK":
                await db.commit()
                raise HTTPException(status_code=403, detail=f"Payout blocked: {risk.reasons}")
            if risk.decision == "REVIEW":
                flags = [str(f) for f in list(o.flags or [])]
                if "MANUAL_REVIEW:PAYOUT" not in flags:
                    flags.append("MANUAL_REVIEW:PAYOUT")
                o.flags = flags
                await db.commit()
                return {"status": "PAYOUT_REVIEW", "reasons": risk.reasons}
        await EscrowService.mark_paid_out(db, o)
        after = {"status": "PAID_OUT", "bif_paid": float(o.bif_paid or 0)}
        actor_id = getattr(current_user, "id", None) or getattr(current_user, "user_id", None)
        await audit_log(
            db,
            actor_user_id=str(actor_id) if actor_id else None,
            actor_role=str(getattr(current_user, "role", "") or ""),
            action="ESCROW_PAYOUT_CONFIRMED",
            entity_type="escrow_order",
            entity_id=str(o.id),
            before_state=before,
            after_state=after,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        return {"status": "PAID_OUT"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/retry", response_model=dict)
async def retry_order_payment(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        o = await EscrowService.get_order(db, order_id)
        current_user_id = str(getattr(current_user, "user_id", ""))
        current_role = str(getattr(current_user, "role", "")).lower()
        is_owner = str(o.user_id) == current_user_id
        if not is_owner and current_role not in {"admin", "agent", "operator"}:
            raise HTTPException(status_code=403, detail="Acces refuse")
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


@router.post("/orders/{order_id}/sandbox/{action}", response_model=dict)
async def sandbox_simulate_transition(
    order_id: str,
    action: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        if not settings.SANDBOX_ENABLED:
            raise HTTPException(status_code=403, detail="Sandbox disabled")
        if settings.SANDBOX_ADMIN_ONLY:
            role = (str(getattr(current_user, "role", "")) or "").strip().lower()
            if role not in {"admin", "operator"}:
                raise HTTPException(status_code=403, detail="Sandbox admin only")

        o = await EscrowService.get_order(db, order_id)
        flags = list(o.flags or [])
        if "SANDBOX" not in flags:
            raise HTTPException(status_code=400, detail="Action reservee au mode sandbox")

        current_status = o.status.value if hasattr(o.status, "value") else str(o.status)
        requested_action = str(action or "").strip().upper()

        if requested_action == "FUND":
            if current_status != "CREATED":
                raise HTTPException(status_code=400, detail=f"Action FUND non autorisee pour status={current_status}")
            o.usdc_received = o.usdc_expected
            o.deposit_confirmations = o.deposit_required_confirmations
            o.funded_at = datetime.now(timezone.utc)
            o.status = EscrowOrderStatus.FUNDED
            await post_funded_usdc_deposit_journal(db, o)

        elif requested_action == "SWAP":
            if current_status != "FUNDED":
                raise HTTPException(status_code=400, detail=f"Action SWAP non autorisee pour status={current_status}")
            o.usdt_received = o.usdc_received or o.usdt_target
            o.conversion_fee_usdt = Decimal("0")
            o.swapped_at = datetime.now(timezone.utc)
            o.status = EscrowOrderStatus.SWAPPED
            await post_swap_usdc_to_usdt_journal(db, o)

        elif requested_action == "PAYOUT_PENDING":
            if current_status != "SWAPPED":
                raise HTTPException(
                    status_code=400,
                    detail=f"Action PAYOUT_PENDING non autorisee pour status={current_status}",
                )
            o.payout_initiated_at = datetime.now(timezone.utc)
            o.status = EscrowOrderStatus.PAYOUT_PENDING

        elif requested_action == "PAYOUT":
            if current_status != "PAYOUT_PENDING":
                raise HTTPException(status_code=400, detail=f"Action PAYOUT non autorisee pour status={current_status}")
            o.bif_paid = o.bif_target
            o.paid_out_at = datetime.now(timezone.utc)
            o.status = EscrowOrderStatus.PAID_OUT
            await on_payout_confirmed(db, o)

        else:
            raise HTTPException(status_code=400, detail=f"Action sandbox inconnue: {requested_action}")

        await db.commit()
        await db.refresh(o)

        return {
            "status": "OK",
            "id": str(o.id),
            "escrow_status": o.status,
            "is_sandbox": "SANDBOX" in list(o.flags or []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
