from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.business_service import (
    _ensure_funding_within_limit,
    _sub_wallet_remaining_capacity,
)


def test_sub_wallet_remaining_capacity_cannot_go_negative():
    assert _sub_wallet_remaining_capacity(current_amount=Decimal("150"), spending_limit=Decimal("100")) == Decimal("0")


def test_sub_wallet_remaining_capacity_returns_expected_amount():
    assert _sub_wallet_remaining_capacity(current_amount=Decimal("35"), spending_limit=Decimal("100")) == Decimal("65")


def test_ensure_funding_within_limit_rejects_over_limit():
    with pytest.raises(HTTPException) as exc:
        _ensure_funding_within_limit(
            current_amount=Decimal("80"),
            spending_limit=Decimal("100"),
            amount=Decimal("25"),
        )
    assert exc.value.status_code == 400
    assert "Plafond du sous-wallet depasse" in str(exc.value.detail)


def test_ensure_funding_within_limit_accepts_exact_remaining():
    _ensure_funding_within_limit(
        current_amount=Decimal("80"),
        spending_limit=Decimal("100"),
        amount=Decimal("20"),
    )
