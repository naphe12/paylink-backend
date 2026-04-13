from decimal import Decimal

from app.services.external_transfer_limits import (
    build_external_transfer_history_stats,
    build_external_transfer_limit_recommendation,
    normalize_external_transfer_limit_policy,
)


def test_normalize_external_transfer_limit_policy_defaults_to_dynamic():
    assert normalize_external_transfer_limit_policy(None) == "dynamic"
    assert normalize_external_transfer_limit_policy("unknown") == "dynamic"
    assert normalize_external_transfer_limit_policy("financial_capacity_only") == "financial_capacity_only"


def test_build_external_transfer_history_stats_computes_percentiles():
    stats = build_external_transfer_history_stats(
        amounts_30d=[Decimal("10"), Decimal("20")],
        amounts_90d=[Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")],
    )
    assert stats.count_30d == 2
    assert stats.count_90d == 5
    assert stats.total_90d == Decimal("150.00")
    assert stats.p50_90d == Decimal("30.00")
    assert stats.p90_90d == Decimal("46.00")


def test_build_external_transfer_limit_recommendation_uses_history():
    stats = build_external_transfer_history_stats(
        amounts_30d=[Decimal("25"), Decimal("30"), Decimal("35"), Decimal("40"), Decimal("50")],
        amounts_90d=[Decimal("20"), Decimal("25"), Decimal("30"), Decimal("35"), Decimal("40"), Decimal("50"), Decimal("60")],
    )
    recommendation = build_external_transfer_limit_recommendation(
        stats=stats,
        current_daily_limit=Decimal("100"),
        current_monthly_limit=Decimal("300"),
        kyc_tier=2,
        risk_score=20,
    )
    assert recommendation["recommended_per_tx"] >= Decimal("50.00")
    assert recommendation["recommended_daily_limit"] >= recommendation["recommended_per_tx"]
    assert recommendation["recommended_monthly_limit"] >= recommendation["recommended_daily_limit"]
    assert recommendation["confidence"] in {"low", "medium", "high"}

