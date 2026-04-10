from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.virtual_cards_service import (
    _card_controls_metadata_payload,
    _extract_card_controls,
    _human_decline_message,
    _validate_card_controls,
)


def test_validate_card_controls_rejects_per_tx_above_daily():
    with pytest.raises(HTTPException) as exc:
        _validate_card_controls(
            per_tx_limit=Decimal("30"),
            daily_limit=Decimal("20"),
            monthly_limit=Decimal("100"),
            spending_limit=Decimal("150"),
        )
    assert exc.value.status_code == 400


def test_validate_card_controls_accepts_consistent_limits():
    _validate_card_controls(
        per_tx_limit=Decimal("20"),
        daily_limit=Decimal("50"),
        monthly_limit=Decimal("100"),
        spending_limit=Decimal("200"),
    )


def test_human_decline_message_for_per_tx_limit():
    assert "par transaction" in _human_decline_message("per_tx_limit_exceeded")


def test_extract_card_controls_exposes_decline_guard():
    fake_card = SimpleNamespace(
        metadata_={
            "controls": _card_controls_metadata_payload(
                per_tx_limit=Decimal("10"),
                daily_limit=Decimal("20"),
                monthly_limit=Decimal("40"),
                blocked_categories=["gaming"],
                max_consecutive_declines=5,
                consecutive_declines=2,
                auto_frozen_for_declines=True,
            )
        }
    )
    controls = _extract_card_controls(fake_card)
    assert controls["max_consecutive_declines"] == 5
    assert controls["consecutive_declines"] == 2
    assert controls["auto_frozen_for_declines"] is True
