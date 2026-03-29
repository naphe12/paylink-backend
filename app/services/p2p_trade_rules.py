from app.models.p2p_enums import TradeStatus


ALLOWED_P2P_TRANSITIONS: dict[TradeStatus, set[TradeStatus]] = {
    TradeStatus.CREATED: {
        TradeStatus.AWAITING_CRYPTO,
        TradeStatus.CANCELLED,
        TradeStatus.EXPIRED,
    },
    TradeStatus.AWAITING_CRYPTO: {
        TradeStatus.CRYPTO_LOCKED,
        TradeStatus.EXPIRED,
        TradeStatus.CANCELLED,
        TradeStatus.DISPUTED,
    },
    TradeStatus.CRYPTO_LOCKED: {
        TradeStatus.AWAITING_FIAT,
        TradeStatus.CANCELLED,
        TradeStatus.DISPUTED,
    },
    TradeStatus.AWAITING_FIAT: {
        TradeStatus.FIAT_SENT,
        TradeStatus.EXPIRED,
        TradeStatus.CANCELLED,
        TradeStatus.DISPUTED,
    },
    TradeStatus.FIAT_SENT: {
        TradeStatus.FIAT_CONFIRMED,
        TradeStatus.CANCELLED,
        TradeStatus.DISPUTED,
    },
    TradeStatus.FIAT_CONFIRMED: {
        TradeStatus.RELEASED,
        TradeStatus.DISPUTED,
    },
    TradeStatus.DISPUTED: {
        TradeStatus.RESOLVED,
        TradeStatus.CANCELLED,
        TradeStatus.RELEASED,
    },
    TradeStatus.RESOLVED: {
        TradeStatus.RELEASED,
        TradeStatus.CANCELLED,
    },
    TradeStatus.RELEASED: set(),
    TradeStatus.CANCELLED: set(),
    TradeStatus.EXPIRED: set(),
}


def validate_trade_transition(from_status: TradeStatus, to_status: TradeStatus) -> None:
    # Idempotent/no-op transition is accepted.
    if from_status == to_status:
        return

    allowed_targets = ALLOWED_P2P_TRANSITIONS.get(from_status, set())
    if to_status in allowed_targets:
        return

    allowed_text = ", ".join(sorted(s.value for s in allowed_targets)) or "none"
    raise ValueError(
        f"Transition P2P invalide: {from_status.value} -> {to_status.value}. "
        f"Transitions autorisees depuis {from_status.value}: {allowed_text}."
    )
