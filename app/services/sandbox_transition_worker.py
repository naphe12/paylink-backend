from sqlalchemy import select
from app.models.escrow_order import EscrowOrder
from app.models.escrow_enums import EscrowOrderStatus
from app.config import settings


def _is_sandbox(order: EscrowOrder) -> bool:
    return "SANDBOX" in list(order.flags or [])


def _scenario(order: EscrowOrder) -> str:
    for flag in list(order.flags or []):
        value = str(flag)
        if value.startswith("SANDBOX_SCENARIO:"):
            return value.split(":", 1)[1].strip().upper()
    return ""


async def run_sandbox_auto_transitions(db):
    if not settings.SANDBOX_ENABLED:
        return

    result = await db.execute(select(EscrowOrder))
    orders = result.scalars().all()

    for order in orders:
        if not _is_sandbox(order):
            continue

        if _scenario(order) != "OK_FAST":
            continue

        if order.status == EscrowOrderStatus.CREATED:
            order.status = EscrowOrderStatus.FUNDED
            order.usdc_received = order.usdc_expected
            order.deposit_confirmations = order.deposit_required_confirmations
        elif order.status == EscrowOrderStatus.FUNDED:
            order.status = EscrowOrderStatus.SWAPPED
            order.usdt_received = order.usdc_received or order.usdt_target
        elif order.status == EscrowOrderStatus.SWAPPED:
            order.bif_paid = order.bif_target
            order.status = EscrowOrderStatus.PAID_OUT

    await db.commit()
