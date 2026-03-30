import pytest

from app.models.escrow_enums import EscrowOrderStatus
from app.models.p2p_enums import TradeStatus
from app.services.escrow_order_rules import (
    ALLOWED_ESCROW_TRANSITIONS,
    transition_escrow_order_status,
    validate_escrow_transition,
)
from app.services.p2p_trade_rules import ALLOWED_P2P_TRANSITIONS, validate_trade_transition


class _EscrowOrder:
    def __init__(self, status):
        self.status = status


@pytest.mark.parametrize(
    ("from_status", "expected_targets"),
    [
        (
            EscrowOrderStatus.CREATED,
            {
                EscrowOrderStatus.FUNDED,
                EscrowOrderStatus.CANCELLED,
                EscrowOrderStatus.EXPIRED,
                EscrowOrderStatus.FAILED,
                EscrowOrderStatus.PAYOUT_PENDING,
            },
        ),
        (
            EscrowOrderStatus.FUNDED,
            {
                EscrowOrderStatus.SWAPPED,
                EscrowOrderStatus.CANCELLED,
                EscrowOrderStatus.FAILED,
                EscrowOrderStatus.REFUND_PENDING,
            },
        ),
        (
            EscrowOrderStatus.SWAPPED,
            {
                EscrowOrderStatus.PAYOUT_PENDING,
                EscrowOrderStatus.PAID_OUT,
                EscrowOrderStatus.CANCELLED,
                EscrowOrderStatus.FAILED,
                EscrowOrderStatus.REFUND_PENDING,
            },
        ),
        (
            EscrowOrderStatus.PAYOUT_PENDING,
            {
                EscrowOrderStatus.PAID_OUT,
                EscrowOrderStatus.CANCELLED,
                EscrowOrderStatus.FAILED,
                EscrowOrderStatus.REFUND_PENDING,
            },
        ),
        (
            EscrowOrderStatus.REFUND_PENDING,
            {
                EscrowOrderStatus.REFUNDED,
                EscrowOrderStatus.FAILED,
            },
        ),
    ],
)
def test_escrow_transition_matrix_matches_expected_targets(from_status, expected_targets):
    assert ALLOWED_ESCROW_TRANSITIONS[from_status] == expected_targets


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (EscrowOrderStatus.CREATED, EscrowOrderStatus.FUNDED),
        (EscrowOrderStatus.FUNDED, EscrowOrderStatus.SWAPPED),
        (EscrowOrderStatus.SWAPPED, EscrowOrderStatus.PAYOUT_PENDING),
        (EscrowOrderStatus.PAYOUT_PENDING, EscrowOrderStatus.PAID_OUT),
        (EscrowOrderStatus.SWAPPED, EscrowOrderStatus.REFUND_PENDING),
        (EscrowOrderStatus.REFUND_PENDING, EscrowOrderStatus.REFUNDED),
    ],
)
def test_escrow_valid_transitions_are_accepted(from_status, to_status):
    validate_escrow_transition(from_status, to_status)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (EscrowOrderStatus.CREATED, EscrowOrderStatus.SWAPPED),
        (EscrowOrderStatus.FUNDED, EscrowOrderStatus.PAID_OUT),
        (EscrowOrderStatus.PAID_OUT, EscrowOrderStatus.REFUND_PENDING),
        (EscrowOrderStatus.REFUNDED, EscrowOrderStatus.PAID_OUT),
    ],
)
def test_escrow_invalid_transitions_raise(from_status, to_status):
    with pytest.raises(ValueError):
        validate_escrow_transition(from_status, to_status)


def test_escrow_transition_updates_order_status():
    order = _EscrowOrder(EscrowOrderStatus.CREATED)
    transition_escrow_order_status(order, EscrowOrderStatus.FUNDED)
    assert order.status == EscrowOrderStatus.FUNDED


@pytest.mark.parametrize(
    ("from_status", "expected_targets"),
    [
        (
            TradeStatus.CREATED,
            {
                TradeStatus.AWAITING_CRYPTO,
                TradeStatus.CANCELLED,
                TradeStatus.EXPIRED,
            },
        ),
        (
            TradeStatus.AWAITING_CRYPTO,
            {
                TradeStatus.CRYPTO_LOCKED,
                TradeStatus.EXPIRED,
                TradeStatus.CANCELLED,
                TradeStatus.DISPUTED,
            },
        ),
        (
            TradeStatus.CRYPTO_LOCKED,
            {
                TradeStatus.AWAITING_FIAT,
                TradeStatus.CANCELLED,
                TradeStatus.DISPUTED,
            },
        ),
        (
            TradeStatus.AWAITING_FIAT,
            {
                TradeStatus.FIAT_SENT,
                TradeStatus.EXPIRED,
                TradeStatus.CANCELLED,
                TradeStatus.DISPUTED,
            },
        ),
        (
            TradeStatus.FIAT_SENT,
            {
                TradeStatus.FIAT_CONFIRMED,
                TradeStatus.CANCELLED,
                TradeStatus.DISPUTED,
            },
        ),
        (
            TradeStatus.FIAT_CONFIRMED,
            {
                TradeStatus.RELEASED,
                TradeStatus.DISPUTED,
            },
        ),
        (
            TradeStatus.DISPUTED,
            {
                TradeStatus.RESOLVED,
                TradeStatus.CANCELLED,
                TradeStatus.RELEASED,
            },
        ),
        (
            TradeStatus.RESOLVED,
            {
                TradeStatus.RELEASED,
                TradeStatus.CANCELLED,
            },
        ),
    ],
)
def test_p2p_transition_matrix_matches_expected_targets(from_status, expected_targets):
    assert ALLOWED_P2P_TRANSITIONS[from_status] == expected_targets


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (TradeStatus.CREATED, TradeStatus.AWAITING_CRYPTO),
        (TradeStatus.AWAITING_CRYPTO, TradeStatus.CRYPTO_LOCKED),
        (TradeStatus.CRYPTO_LOCKED, TradeStatus.AWAITING_FIAT),
        (TradeStatus.AWAITING_FIAT, TradeStatus.FIAT_SENT),
        (TradeStatus.FIAT_SENT, TradeStatus.FIAT_CONFIRMED),
        (TradeStatus.FIAT_CONFIRMED, TradeStatus.RELEASED),
        (TradeStatus.DISPUTED, TradeStatus.RESOLVED),
    ],
)
def test_p2p_valid_transitions_are_accepted(from_status, to_status):
    validate_trade_transition(from_status, to_status)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (TradeStatus.CREATED, TradeStatus.RELEASED),
        (TradeStatus.AWAITING_CRYPTO, TradeStatus.FIAT_SENT),
        (TradeStatus.CRYPTO_LOCKED, TradeStatus.FIAT_SENT),
        (TradeStatus.FIAT_SENT, TradeStatus.RELEASED),
        (TradeStatus.RELEASED, TradeStatus.DISPUTED),
        (TradeStatus.CANCELLED, TradeStatus.RELEASED),
    ],
)
def test_p2p_invalid_transitions_raise(from_status, to_status):
    with pytest.raises(ValueError):
        validate_trade_transition(from_status, to_status)
