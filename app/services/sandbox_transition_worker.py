from sqlalchemy import select
from app.models.escrow_order import EscrowOrder
from app.models.escrow_enums import EscrowOrderStatus
from app.config import settings
from app.services.escrow_tracking_ws import broadcast_tracking_update
from app.services.escrow_order_rules import transition_escrow_order_status


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

    result = await db.execute(
        select(EscrowOrder)
        .where(
            EscrowOrder.flags.any("SANDBOX"),
            EscrowOrder.status.in_(
                [
                    EscrowOrderStatus.CREATED,
                    EscrowOrderStatus.FUNDED,
                    EscrowOrderStatus.SWAPPED,
                ]
            ),
        )
        .limit(200)
    )
    orders = result.scalars().all()
    changed = False
    changed_orders: list[EscrowOrder] = []

    for order in orders:
        if not _is_sandbox(order):
            continue

        if _scenario(order) != "OK_FAST":
            continue

        if order.status == EscrowOrderStatus.CREATED:
            transition_escrow_order_status(order, EscrowOrderStatus.FUNDED)
            order.usdc_received = order.usdc_expected
            order.deposit_confirmations = order.deposit_required_confirmations
            changed = True
            changed_orders.append(order)
        elif order.status == EscrowOrderStatus.FUNDED:
            transition_escrow_order_status(order, EscrowOrderStatus.SWAPPED)
            order.usdt_received = order.usdc_received or order.usdt_target
            changed = True
            changed_orders.append(order)
        elif order.status == EscrowOrderStatus.SWAPPED:
            order.bif_paid = order.bif_target
            transition_escrow_order_status(order, EscrowOrderStatus.PAID_OUT)
            changed = True
            changed_orders.append(order)

    if changed:
        await db.commit()
        for order in changed_orders:
            await broadcast_tracking_update(order)
    else:
        await db.rollback()
