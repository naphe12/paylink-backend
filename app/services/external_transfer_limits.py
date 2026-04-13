from __future__ import annotations

import decimal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_transfers import ExternalTransfers
from app.models.wallets import Wallets
from app.routers.ref.exchange import _resolve_exchange_rate


SUCCESSFUL_EXTERNAL_TRANSFER_STATUSES = {"approved", "completed", "succeeded"}
DECIMAL_ZERO = decimal.Decimal("0")


def normalize_external_transfer_limit_policy(raw_policy: str | None) -> str:
    value = str(raw_policy or "").strip().lower()
    if value in {"financial_capacity_only", "capacity_only", "financial_only"}:
        return "financial_capacity_only"
    if value in {"dynamic", "history_based", "historical"}:
        return "dynamic"
    return "dynamic"


def _safe_decimal(value) -> decimal.Decimal:
    try:
        return decimal.Decimal(str(value or 0))
    except Exception:
        return DECIMAL_ZERO


def _percentile(values: list[decimal.Decimal], p: float) -> decimal.Decimal:
    if not values:
        return DECIMAL_ZERO
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * max(0.0, min(1.0, p))
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    if low == high:
        return sorted_values[low]
    weight = decimal.Decimal(str(rank - low))
    return (sorted_values[low] * (decimal.Decimal("1") - weight)) + (sorted_values[high] * weight)


def _quantize_2(value: decimal.Decimal) -> decimal.Decimal:
    return max(value, DECIMAL_ZERO).quantize(decimal.Decimal("0.01"))


def _as_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _get_user_reference_currency(db: AsyncSession, *, user_id) -> str:
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    wallet = await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
    )
    return str(getattr(wallet, "currency_code", None) or "EUR").upper()


def _extract_transfer_currency(transfer_currency, metadata) -> str:
    meta = dict(metadata or {})
    return str(meta.get("origin_currency") or transfer_currency or "EUR").upper()


@dataclass
class ExternalTransferHistoryStats:
    count_30d: int
    count_90d: int
    total_30d: decimal.Decimal
    total_90d: decimal.Decimal
    avg_90d: decimal.Decimal
    p50_90d: decimal.Decimal
    p90_90d: decimal.Decimal
    max_90d: decimal.Decimal


def build_external_transfer_history_stats(
    amounts_30d: Iterable[decimal.Decimal],
    amounts_90d: Iterable[decimal.Decimal],
) -> ExternalTransferHistoryStats:
    values_30 = [max(_safe_decimal(v), DECIMAL_ZERO) for v in amounts_30d]
    values_90 = [max(_safe_decimal(v), DECIMAL_ZERO) for v in amounts_90d]
    total_30 = sum(values_30, DECIMAL_ZERO)
    total_90 = sum(values_90, DECIMAL_ZERO)
    count_30 = len(values_30)
    count_90 = len(values_90)
    avg_90 = (total_90 / decimal.Decimal(count_90)) if count_90 else DECIMAL_ZERO
    return ExternalTransferHistoryStats(
        count_30d=count_30,
        count_90d=count_90,
        total_30d=_quantize_2(total_30),
        total_90d=_quantize_2(total_90),
        avg_90d=_quantize_2(avg_90),
        p50_90d=_quantize_2(_percentile(values_90, 0.50)),
        p90_90d=_quantize_2(_percentile(values_90, 0.90)),
        max_90d=_quantize_2(max(values_90) if values_90 else DECIMAL_ZERO),
    )


def build_external_transfer_limit_recommendation(
    *,
    stats: ExternalTransferHistoryStats,
    current_daily_limit: decimal.Decimal,
    current_monthly_limit: decimal.Decimal,
    kyc_tier: int,
    risk_score: int,
) -> dict:
    current_daily = max(_safe_decimal(current_daily_limit), DECIMAL_ZERO)
    current_monthly = max(_safe_decimal(current_monthly_limit), DECIMAL_ZERO)
    tier = max(int(kyc_tier or 0), 0)
    risk = max(int(risk_score or 0), 0)

    if stats.count_90d == 0:
        seeded_daily = current_daily if current_daily > 0 else decimal.Decimal("100")
        seeded_monthly = current_monthly if current_monthly > 0 else seeded_daily * decimal.Decimal("20")
        seeded_per_tx = max(seeded_daily / decimal.Decimal("3"), decimal.Decimal("20"))
        return {
            "recommended_per_tx": _quantize_2(seeded_per_tx),
            "recommended_daily_limit": _quantize_2(seeded_daily),
            "recommended_monthly_limit": _quantize_2(max(seeded_monthly, seeded_daily)),
            "confidence": "low",
            "confidence_score": 25,
            "explanations": [
                "Historique insuffisant, recommandation basee sur les limites actuelles.",
            ],
        }

    # Requested product rule:
    # - daily limit = historical average transfer amount
    # - monthly limit = daily limit * 30
    avg_per_transfer = _quantize_2(stats.avg_90d)
    recommended_per_tx = max(avg_per_transfer, decimal.Decimal("5.00"))
    recommended_daily = recommended_per_tx
    recommended_monthly = _quantize_2(recommended_daily * decimal.Decimal("30"))

    confidence_score = min(100, (stats.count_90d * 5) + (20 if stats.count_30d >= 6 else 0))
    confidence = "high" if confidence_score >= 70 else "medium" if confidence_score >= 45 else "low"

    explanations: list[str] = [
        (
            "Base tout historique: "
            f"total={stats.total_90d}, nombre_transferts={stats.count_90d}, "
            f"moyenne_par_transfert={avg_per_transfer}."
        ),
        "Regle active: limite_jour = moyenne historique, limite_mois = limite_jour x 30.",
        f"Contexte profil (informatif): kyc_tier={tier}, risk_score={risk}.",
    ]

    return {
        "recommended_per_tx": recommended_per_tx,
        "recommended_daily_limit": max(recommended_daily, decimal.Decimal("5.00")),
        "recommended_monthly_limit": max(recommended_monthly, decimal.Decimal("150.00")),
        "confidence": confidence,
        "confidence_score": confidence_score,
        "calculation_inputs": {
            "total_all": str(stats.total_90d),
            "count_all": stats.count_90d,
            "avg_per_transfer": str(avg_per_transfer),
            "formula": "avg_per_transfer = total_all / count_all; daily = avg_per_transfer; monthly = daily * 30",
        },
        "explanations": explanations,
    }


async def build_user_external_transfer_limit_analysis(
    db: AsyncSession,
    *,
    user_id,
    current_daily_limit: decimal.Decimal,
    current_monthly_limit: decimal.Decimal,
    kyc_tier: int,
    risk_score: int,
    window_days: int = 90,
) -> dict:
    now = datetime.now(timezone.utc)
    since_90 = now - timedelta(days=max(int(window_days or 90), 1))
    since_30 = now - timedelta(days=30)
    reference_currency = await _get_user_reference_currency(db, user_id=user_id)

    rows = (
        await db.execute(
            select(
                ExternalTransfers.amount,
                ExternalTransfers.created_at,
                ExternalTransfers.currency,
                ExternalTransfers.local_amount,
                ExternalTransfers.metadata_,
            )
            .where(
                ExternalTransfers.user_id == user_id,
                ExternalTransfers.status.in_(SUCCESSFUL_EXTERNAL_TRANSFER_STATUSES),
            )
            .order_by(ExternalTransfers.created_at.desc())
        )
    ).all()

    fx_cache: dict[tuple[str, str], decimal.Decimal | None] = {}
    converted_count = 0
    unconverted_count = 0
    amounts_all: list[decimal.Decimal] = []
    amounts_90d: list[decimal.Decimal] = []
    amounts_30d: list[decimal.Decimal] = []
    for amount, created_at, transfer_currency, local_amount, metadata in rows:
        raw_amount = max(_safe_decimal(amount), DECIMAL_ZERO)
        source_currency = _extract_transfer_currency(transfer_currency, metadata)
        normalized_value = raw_amount
        if source_currency != reference_currency:
            pair = (source_currency, reference_currency)
            if pair not in fx_cache:
                rate, _ = await _resolve_exchange_rate(db, source_currency, reference_currency)
                fx_cache[pair] = _safe_decimal(rate) if rate else None
            rate_used = fx_cache.get(pair)
            if rate_used and rate_used > DECIMAL_ZERO:
                normalized_value = _quantize_2(raw_amount * rate_used)
                converted_count += 1
            else:
                meta = dict(metadata or {})
                destination_currency = str(meta.get("destination_currency") or "BIF").upper()
                if destination_currency == reference_currency and local_amount is not None:
                    normalized_value = max(_safe_decimal(local_amount), DECIMAL_ZERO)
                    converted_count += 1
                else:
                    # Keep backward-compatible fallback when no FX path exists.
                    unconverted_count += 1
        else:
            converted_count += 1

        value = normalized_value
        amounts_all.append(value)
        created_at_utc = _as_utc_aware(created_at)
        if created_at_utc and created_at_utc >= since_90:
            amounts_90d.append(value)
        if created_at_utc and created_at_utc >= since_30:
            amounts_30d.append(value)

    stats_recent = build_external_transfer_history_stats(amounts_30d, amounts_90d)
    stats_all = build_external_transfer_history_stats(amounts_all, amounts_all)
    recommendation = build_external_transfer_limit_recommendation(
        stats=stats_all,
        current_daily_limit=current_daily_limit,
        current_monthly_limit=current_monthly_limit,
        kyc_tier=kyc_tier,
        risk_score=risk_score,
    )
    return {
        "window_days": int(window_days or 90),
        "aggregation_currency": reference_currency,
        "conversion": {
            "converted_count": converted_count,
            "unconverted_count": unconverted_count,
        },
        "history": {
            "count_30d": stats_recent.count_30d,
            "count_90d": stats_recent.count_90d,
            "total_30d": str(stats_recent.total_30d),
            "total_90d": str(stats_recent.total_90d),
            "avg_90d": str(stats_recent.avg_90d),
            "p50_90d": str(stats_recent.p50_90d),
            "p90_90d": str(stats_recent.p90_90d),
            "max_90d": str(stats_recent.max_90d),
            "count_all": stats_all.count_90d,
            "total_all": str(stats_all.total_90d),
            "avg_all": str(stats_all.avg_90d),
            "p50_all": str(stats_all.p50_90d),
            "p90_all": str(stats_all.p90_90d),
            "max_all": str(stats_all.max_90d),
        },
        "recommendation": {
            "recommended_per_tx": str(recommendation["recommended_per_tx"]),
            "recommended_daily_limit": str(recommendation["recommended_daily_limit"]),
            "recommended_monthly_limit": str(recommendation["recommended_monthly_limit"]),
            "confidence": recommendation["confidence"],
            "confidence_score": recommendation["confidence_score"],
            "scope": "all_history",
            "calculation_inputs": recommendation.get("calculation_inputs") or {},
            "explanations": recommendation["explanations"],
        },
    }
