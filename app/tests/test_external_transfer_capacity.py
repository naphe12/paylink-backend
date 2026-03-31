from decimal import Decimal

from app.services.external_transfer_capacity import (
    compute_external_transfer_funding,
    effective_external_transfer_capacity,
)


def test_effective_external_transfer_capacity_uses_wallet_plus_credit_when_wallet_positive():
    assert effective_external_transfer_capacity(Decimal("25"), Decimal("80")) == Decimal("105")


def test_effective_external_transfer_capacity_uses_only_credit_when_wallet_negative():
    assert effective_external_transfer_capacity(Decimal("-25"), Decimal("80")) == Decimal("80")


def test_compute_external_transfer_funding_does_not_push_wallet_below_zero():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("25"),
        credit_available=Decimal("80"),
        total_required=Decimal("40"),
    )

    assert funding["wallet_debit_amount"] == Decimal("25")
    assert funding["wallet_after"] == Decimal("0")
    assert funding["credit_used"] == Decimal("15")
    assert funding["credit_available_after"] == Decimal("65")


def test_compute_external_transfer_funding_keeps_negative_wallet_unchanged():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("-25"),
        credit_available=Decimal("80"),
        total_required=Decimal("40"),
    )

    assert funding["wallet_debit_amount"] == Decimal("0")
    assert funding["wallet_after"] == Decimal("-25")
    assert funding["credit_used"] == Decimal("40")
    assert funding["credit_available_after"] == Decimal("40")
