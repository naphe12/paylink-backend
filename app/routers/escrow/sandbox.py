from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.escrow_enums import EscrowOrderStatus
from app.models.escrow_order import EscrowOrder
from app.models.users import Users
from app.services.escrow_ledger_hooks import (
    on_payout_confirmed,
    post_funded_usdc_deposit_journal,
    post_swap_usdc_to_usdt_journal,
)

router = APIRouter(prefix="/api/escrow/sandbox", tags=["Escrow Sandbox"])


def _is_sandbox_order(order: EscrowOrder) -> bool:
    return "SANDBOX" in list(order.flags or [])


def _get_flag_value(order: EscrowOrder, prefix: str, default: str = "") -> str:
    for flag in list(order.flags or []):
        text = str(flag)
        if text.startswith(prefix):
            return text.split(":", 1)[1]
    return default


def _set_flag_value(order: EscrowOrder, prefix: str, value: str) -> None:
    flags = [str(f) for f in list(order.flags or []) if not str(f).startswith(prefix)]
    flags.append(f"{prefix}{value}")
    order.flags = flags


def _get_sandbox_scenario(order: EscrowOrder) -> str:
    return _get_flag_value(order, "SANDBOX_SCENARIO:", "").strip().upper()


def _get_sandbox_step(order: EscrowOrder) -> int:
    raw = _get_flag_value(order, "SANDBOX_STEP:", "0")
    try:
        return int(raw)
    except Exception:
        return 0


def _set_sandbox_step(order: EscrowOrder, step: int) -> None:
    _set_flag_value(order, "SANDBOX_STEP:", str(step))


def guard_sandbox(user: Users | None) -> None:
    if not settings.SANDBOX_ENABLED:
        raise HTTPException(status_code=403, detail="Sandbox disabled")

    if settings.SANDBOX_ADMIN_ONLY:
        role = (str(getattr(user, "role", "")) or "").strip().lower()
        if role not in {"admin", "operator"}:
            raise HTTPException(status_code=403, detail="Sandbox admin only")


# ----------------------------------------------------
# FUND
# ----------------------------------------------------
@router.post("/orders/{order_id}/fund")
async def sandbox_fund(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    guard_sandbox(user)

    result = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
    order = result.scalar_one_or_none()

    if not order or not _is_sandbox_order(order):
        raise HTTPException(status_code=400, detail="Invalid sandbox order")

    if order.status != EscrowOrderStatus.CREATED:
        raise HTTPException(status_code=400, detail="Order not in CREATED state")

    if _get_sandbox_scenario(order) == "WEBHOOK_FAIL_ONCE" and _get_sandbox_step(order) == 0:
        _set_sandbox_step(order, 1)
        await db.commit()
        raise HTTPException(status_code=500, detail="Simulated webhook failure")

    order.usdc_received = order.usdc_expected
    order.deposit_confirmations = order.deposit_required_confirmations
    order.status = EscrowOrderStatus.FUNDED
    _set_sandbox_step(order, 1)

    await post_funded_usdc_deposit_journal(db, order)
    await db.commit()

    return {"status": "FUNDED"}


# ----------------------------------------------------
# SWAP
# ----------------------------------------------------
@router.post("/orders/{order_id}/swap")
async def sandbox_swap(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    guard_sandbox(user)

    result = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
    order = result.scalar_one_or_none()

    if not order or not _is_sandbox_order(order):
        raise HTTPException(status_code=400, detail="Invalid sandbox order")

    if order.status != EscrowOrderStatus.FUNDED:
        raise HTTPException(status_code=400, detail="Order must be FUNDED")

    if _get_sandbox_scenario(order) == "SWAP_FAILED":
        raise HTTPException(status_code=500, detail="Simulated swap failure")

    order.usdt_received = order.usdc_received or order.usdt_target
    order.conversion_fee_usdt = (order.usdt_received * Decimal("0.01")).quantize(Decimal("0.00000001"))
    order.status = EscrowOrderStatus.SWAPPED
    _set_sandbox_step(order, 2)

    await post_swap_usdc_to_usdt_journal(db, order)
    await db.commit()

    return {"status": "SWAPPED"}


# ----------------------------------------------------
# PAYOUT
# ----------------------------------------------------
@router.post("/orders/{order_id}/payout")
async def sandbox_payout(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    guard_sandbox(user)

    result = await db.execute(select(EscrowOrder).where(EscrowOrder.id == order_id))
    order = result.scalar_one_or_none()

    if not order or not _is_sandbox_order(order):
        raise HTTPException(status_code=400, detail="Invalid sandbox order")

    if order.status != EscrowOrderStatus.SWAPPED:
        raise HTTPException(status_code=400, detail="Order must be SWAPPED")

    if _get_sandbox_scenario(order) == "PAYOUT_STUCK":
        order.status = EscrowOrderStatus.PAYOUT_PENDING
        await db.commit()
        return {"status": "PAYOUT_PENDING"}

    order.bif_paid = order.bif_target
    order.status = EscrowOrderStatus.PAID_OUT
    _set_sandbox_step(order, 3)

    await on_payout_confirmed(db, order)
    await db.commit()

    return {"status": "PAID_OUT"}
