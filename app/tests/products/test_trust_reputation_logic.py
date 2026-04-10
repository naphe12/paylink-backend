from decimal import Decimal

from app.services.trust_service_v2 import _compute_ratio, _derive_reputation


def test_compute_ratio_handles_empty_denominator():
    assert _compute_ratio(3, 0) is None


def test_compute_ratio_returns_quantized_decimal():
    assert _compute_ratio(7, 8) == Decimal("0.8750")


def test_derive_reputation_returns_excellent_for_low_dispute_and_high_score():
    tier, note = _derive_reputation(
        trust_score=85,
        p2p_dispute_rate=Decimal("0.01"),
        successful_p2p_trades=7,
    )
    assert tier == "excellent"
    assert "fiable" in note


def test_derive_reputation_returns_watch_for_low_score():
    tier, _ = _derive_reputation(
        trust_score=25,
        p2p_dispute_rate=Decimal("0.20"),
        successful_p2p_trades=2,
    )
    assert tier == "watch"
