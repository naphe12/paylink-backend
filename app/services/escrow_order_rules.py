from app.models.escrow_enums import EscrowOrderStatus
from app.models.escrow_order import EscrowOrder


ALLOWED_ESCROW_TRANSITIONS: dict[EscrowOrderStatus, set[EscrowOrderStatus]] = {
    EscrowOrderStatus.CREATED: {
        EscrowOrderStatus.FUNDED,
        EscrowOrderStatus.CANCELLED,
        EscrowOrderStatus.EXPIRED,
        EscrowOrderStatus.FAILED,
        EscrowOrderStatus.PAYOUT_PENDING,  # sandbox/manual ops only
    },
    EscrowOrderStatus.FUNDED: {
        EscrowOrderStatus.SWAPPED,
        EscrowOrderStatus.CANCELLED,
        EscrowOrderStatus.FAILED,
        EscrowOrderStatus.REFUND_PENDING,
    },
    EscrowOrderStatus.SWAPPED: {
        EscrowOrderStatus.PAYOUT_PENDING,
        EscrowOrderStatus.PAID_OUT,
        EscrowOrderStatus.CANCELLED,
        EscrowOrderStatus.FAILED,
        EscrowOrderStatus.REFUND_PENDING,
    },
    EscrowOrderStatus.PAYOUT_PENDING: {
        EscrowOrderStatus.PAID_OUT,
        EscrowOrderStatus.CANCELLED,
        EscrowOrderStatus.FAILED,
        EscrowOrderStatus.REFUND_PENDING,
    },
    EscrowOrderStatus.REFUND_PENDING: {
        EscrowOrderStatus.REFUNDED,
        EscrowOrderStatus.FAILED,
    },
    EscrowOrderStatus.PAID_OUT: set(),
    EscrowOrderStatus.CANCELLED: set(),
    EscrowOrderStatus.EXPIRED: set(),
    EscrowOrderStatus.REFUNDED: set(),
    EscrowOrderStatus.FAILED: set(),
}


def validate_escrow_transition(from_status: EscrowOrderStatus, to_status: EscrowOrderStatus) -> None:
    if from_status == to_status:
        return
    allowed = ALLOWED_ESCROW_TRANSITIONS.get(from_status, set())
    if to_status in allowed:
        return
    allowed_text = ", ".join(sorted(s.value for s in allowed)) or "none"
    raise ValueError(
        f"Transition escrow invalide: {from_status.value} -> {to_status.value}. "
        f"Transitions autorisees depuis {from_status.value}: {allowed_text}."
    )


def transition_escrow_order_status(
    order: EscrowOrder,
    to_status: EscrowOrderStatus,
    *,
    force: bool = False,
) -> None:
    from_status = order.status
    if not force:
        validate_escrow_transition(from_status, to_status)
    order.status = to_status
