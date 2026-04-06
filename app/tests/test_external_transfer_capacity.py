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


def test_compute_external_transfer_funding_uses_credit_first_for_negative_wallet():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("-25"),
        credit_available=Decimal("80"),
        total_required=Decimal("40"),
    )

    assert funding["wallet_debit_amount"] == Decimal("0")
    assert funding["wallet_after"] == Decimal("-25")
    assert funding["credit_used"] == Decimal("40")
    assert funding["credit_available_after"] == Decimal("40")


def test_compute_external_transfer_funding_pushes_negative_wallet_only_for_uncovered_residual():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("-25"),
        credit_available=Decimal("80"),
        total_required=Decimal("100"),
    )

    assert funding["wallet_debit_amount"] == Decimal("20")
    assert funding["wallet_after"] == Decimal("-45")
    assert funding["credit_used"] == Decimal("80")
    assert funding["credit_available_after"] == Decimal("0")


def test_compute_external_transfer_funding_can_force_credit_only_for_bif_wallets():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("25"),
        credit_available=Decimal("80"),
        total_required=Decimal("40"),
        prefer_credit_only=True,
    )

    assert funding["wallet_debit_amount"] == Decimal("0")
    assert funding["wallet_after"] == Decimal("25")
    assert funding["credit_used"] == Decimal("40")
    assert funding["credit_available_after"] == Decimal("40")


def test_compute_external_transfer_funding_can_mirror_wallet_and_credit_for_eur_clients():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("25"),
        credit_available=Decimal("80"),
        total_required=Decimal("40"),
        mirror_wallet_with_credit=True,
    )

    assert funding["wallet_debit_amount"] == Decimal("40")
    assert funding["wallet_after"] == Decimal("-15")
    assert funding["credit_used"] == Decimal("40")
    assert funding["credit_available_after"] == Decimal("40")


def test_compute_external_transfer_funding_mirrors_wallet_even_when_credit_only_covers_shortage():
    funding = compute_external_transfer_funding(
        wallet_available=Decimal("25"),
        credit_available=Decimal("15"),
        total_required=Decimal("40"),
        mirror_wallet_with_credit=True,
    )

    assert funding["wallet_debit_amount"] == Decimal("40")
    assert funding["wallet_after"] == Decimal("-15")
    assert funding["credit_used"] == Decimal("15")
    assert funding["credit_available_after"] == Decimal("0")
