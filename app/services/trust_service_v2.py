from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disputes import Disputes
from app.models.payment_requests import PaymentRequests
from app.models.trust_badges import TrustBadges
from app.models.trust_events import TrustEvents
from app.models.trust_profiles import TrustProfiles
from app.models.user_trust_badges import UserTrustBadges
from app.models.users import Users

TRUST_PROFILE_STALE_AFTER = timedelta(hours=24)
KYC_TIER_LIMITS = {
    0: (Decimal("30000"), Decimal("30000")),
    1: (Decimal("1000000"), Decimal("5000000")),
    2: (Decimal("10000000"), Decimal("30000000")),
    3: (Decimal("999999999"), Decimal("999999999")),
}
TRUST_LIMIT_MULTIPLIERS = {
    "new": Decimal("1.00"),
    "verified": Decimal("1.10"),
    "trusted": Decimal("1.25"),
    "premium_trusted": Decimal("1.50"),
    "restricted": Decimal("1.00"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_level(score: int) -> str:
    if score < 20:
        return "new"
    if score < 50:
        return "verified"
    if score < 75:
        return "trusted"
    return "premium_trusted"


def _score_profile(
    *,
    kyc_verified: bool,
    account_age_days: int,
    successful_payment_requests: int,
    successful_p2p_trades: int,
    dispute_count: int,
    failed_obligation_count: int,
    chargeback_like_count: int,
) -> int:
    score = 10
    if kyc_verified:
        score += 15
    score += min(20, account_age_days // 30 * 2)
    score += min(20, successful_payment_requests * 2)
    score += min(15, successful_p2p_trades * 3)
    score -= min(25, dispute_count * 8)
    score -= min(15, failed_obligation_count * 5)
    score -= min(20, chargeback_like_count * 10)
    return max(0, min(100, int(score)))


async def _ensure_badge_catalog(db: AsyncSession) -> None:
    badges = [
        ("kyc_verified", "KYC verifie", "Identite verifiee avec succes."),
        ("reliable_payer", "Payeur fiable", "Historique solide de demandes reglees."),
        ("seasoned_user", "Utilisateur etabli", "Compte actif depuis plusieurs mois."),
    ]
    for badge_code, name, description in badges:
        existing = await db.scalar(select(TrustBadges).where(TrustBadges.badge_code == badge_code))
        if not existing:
            db.add(TrustBadges(badge_code=badge_code, name=name, description=description, metadata_={}))
    await db.flush()


async def _set_badge(db: AsyncSession, *, user_id: UUID, badge_code: str, enabled: bool) -> None:
    record = await db.scalar(
        select(UserTrustBadges).where(UserTrustBadges.user_id == user_id, UserTrustBadges.badge_code == badge_code)
    )
    if enabled:
        if not record:
            db.add(UserTrustBadges(user_id=user_id, badge_code=badge_code, metadata_={}))
        elif record.revoked_at is not None:
            record.revoked_at = None
    elif record and record.revoked_at is None:
        record.revoked_at = _utcnow()
    await db.flush()


async def _collect_badges(db: AsyncSession, *, user_id: UUID) -> list[dict]:
    rows = await db.execute(
        select(UserTrustBadges, TrustBadges)
        .join(TrustBadges, TrustBadges.badge_code == UserTrustBadges.badge_code)
        .where(UserTrustBadges.user_id == user_id, UserTrustBadges.revoked_at.is_(None))
        .order_by(UserTrustBadges.granted_at.asc())
    )
    return [
        {
            "badge_code": badge.badge_code,
            "name": badge.name,
            "description": badge.description,
            "granted_at": user_badge.granted_at,
        }
        for user_badge, badge in rows.all()
    ]


def _compute_limit_multiplier(*, trust_level: str, trust_score: int, kyc_verified: bool, kyc_tier: int) -> Decimal:
    if not kyc_verified:
        return Decimal("1.00")
    if int(kyc_tier or 0) >= 3:
        return Decimal("1.00")

    base_multiplier = TRUST_LIMIT_MULTIPLIERS.get(str(trust_level or "").lower(), Decimal("1.00"))
    score_bonus = Decimal("0.00")
    if trust_level in {"trusted", "premium_trusted"} and trust_score > 70:
        score_bonus = min(Decimal("0.10"), Decimal(trust_score - 70) / Decimal("100"))
    multiplier = base_multiplier + score_bonus
    return max(Decimal("1.00"), multiplier)


def _compute_recommended_limits(*, kyc_tier: int, trust_level: str, trust_score: int, kyc_verified: bool) -> tuple[Decimal, Decimal, Decimal]:
    normalized_tier = int(kyc_tier or 0)
    base_daily, base_monthly = KYC_TIER_LIMITS.get(normalized_tier, KYC_TIER_LIMITS[0])
    multiplier = _compute_limit_multiplier(
        trust_level=trust_level,
        trust_score=trust_score,
        kyc_verified=kyc_verified,
        kyc_tier=normalized_tier,
    )
    if normalized_tier >= 3:
        return multiplier, base_daily, base_monthly

    daily_limit = (base_daily * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    monthly_limit = (base_monthly * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return multiplier, daily_limit, monthly_limit


async def _serialize_profile(db: AsyncSession, profile: TrustProfiles, *, user: Users | None = None) -> dict:
    if user is None:
        user = await db.scalar(select(Users).where(Users.user_id == profile.user_id))
    metadata = dict(profile.metadata_ or {})
    current_daily_limit = Decimal(str(getattr(user, "daily_limit", 0) or 0)) if user else None
    current_monthly_limit = Decimal(str(getattr(user, "monthly_limit", 0) or 0)) if user else None
    recommended_daily_limit = metadata.get("recommended_daily_limit")
    recommended_monthly_limit = metadata.get("recommended_monthly_limit")
    limit_multiplier = metadata.get("limit_multiplier")
    return {
        "user_id": profile.user_id,
        "trust_score": int(profile.trust_score or 0),
        "trust_level": profile.trust_level,
        "kyc_tier": int(getattr(user, "kyc_tier", 0) or 0) if user else None,
        "successful_payment_requests": int(profile.successful_payment_requests or 0),
        "successful_p2p_trades": int(profile.successful_p2p_trades or 0),
        "dispute_count": int(profile.dispute_count or 0),
        "failed_obligation_count": int(profile.failed_obligation_count or 0),
        "chargeback_like_count": int(profile.chargeback_like_count or 0),
        "kyc_verified": bool(profile.kyc_verified),
        "account_age_days": int(profile.account_age_days or 0),
        "current_daily_limit": current_daily_limit,
        "current_monthly_limit": current_monthly_limit,
        "recommended_daily_limit": Decimal(str(recommended_daily_limit)) if recommended_daily_limit is not None else None,
        "recommended_monthly_limit": Decimal(str(recommended_monthly_limit)) if recommended_monthly_limit is not None else None,
        "limit_multiplier": Decimal(str(limit_multiplier)) if limit_multiplier is not None else None,
        "limit_uplift_active": bool(metadata.get("limit_uplift_active", False)),
        "auto_limit_applied_at": metadata.get("auto_limit_applied_at"),
        "last_computed_at": profile.last_computed_at,
        "metadata": metadata,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "badges": await _collect_badges(db, user_id=profile.user_id),
    }


async def recompute_trust_profile(db: AsyncSession, *, user_id: UUID) -> dict:
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    await _ensure_badge_catalog(db)

    successful_payment_requests = int(
        (
            await db.execute(
                select(func.count())
                .select_from(PaymentRequests)
                .where(PaymentRequests.requester_user_id == user_id, PaymentRequests.status == "paid")
            )
        ).scalar_one()
        or 0
    )
    dispute_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Disputes)
                .where(Disputes.opened_by == user_id)
            )
        ).scalar_one()
        or 0
    )
    account_age_days = 0
    if getattr(user, "created_at", None):
        created_at = user.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        account_age_days = max(0, (_utcnow() - created_at).days)

    kyc_verified = str(getattr(user, "kyc_status", "")).lower().endswith("verified")
    successful_p2p_trades = 0
    failed_obligation_count = 0
    chargeback_like_count = 0

    score = _score_profile(
        kyc_verified=kyc_verified,
        account_age_days=account_age_days,
        successful_payment_requests=successful_payment_requests,
        successful_p2p_trades=successful_p2p_trades,
        dispute_count=dispute_count,
        failed_obligation_count=failed_obligation_count,
        chargeback_like_count=chargeback_like_count,
    )
    level = _compute_level(score)
    kyc_tier = int(getattr(user, "kyc_tier", 0) or 0)
    limit_multiplier, recommended_daily_limit, recommended_monthly_limit = _compute_recommended_limits(
        kyc_tier=kyc_tier,
        trust_level=level,
        trust_score=score,
        kyc_verified=kyc_verified,
    )

    profile = await db.scalar(select(TrustProfiles).where(TrustProfiles.user_id == user_id))
    previous_score = int(profile.trust_score or 0) if profile else 0
    now = _utcnow()

    if not profile:
        profile = TrustProfiles(
            user_id=user_id,
            created_at=now,
            updated_at=now,
            metadata_={},
        )
        db.add(profile)

    base_daily_limit, base_monthly_limit = KYC_TIER_LIMITS.get(kyc_tier, KYC_TIER_LIMITS[0])
    current_daily_limit = Decimal(str(getattr(user, "daily_limit", 0) or 0))
    current_monthly_limit = Decimal(str(getattr(user, "monthly_limit", 0) or 0))
    next_daily_limit = max(current_daily_limit, recommended_daily_limit)
    next_monthly_limit = max(current_monthly_limit, recommended_monthly_limit)
    limit_uplift_active = recommended_daily_limit > base_daily_limit or recommended_monthly_limit > base_monthly_limit
    auto_limit_applied = next_daily_limit > current_daily_limit or next_monthly_limit > current_monthly_limit
    if auto_limit_applied:
        user.daily_limit = next_daily_limit
        user.monthly_limit = next_monthly_limit

    profile.trust_score = score
    profile.trust_level = level
    profile.successful_payment_requests = successful_payment_requests
    profile.successful_p2p_trades = successful_p2p_trades
    profile.dispute_count = dispute_count
    profile.failed_obligation_count = failed_obligation_count
    profile.chargeback_like_count = chargeback_like_count
    profile.kyc_verified = kyc_verified
    profile.account_age_days = account_age_days
    profile.last_computed_at = now
    profile.metadata_ = {
        **dict(profile.metadata_ or {}),
        "limit_multiplier": str(limit_multiplier),
        "recommended_daily_limit": str(recommended_daily_limit),
        "recommended_monthly_limit": str(recommended_monthly_limit),
        "limit_uplift_active": limit_uplift_active,
        "auto_limit_applied_at": now.isoformat() if auto_limit_applied else (profile.metadata_ or {}).get("auto_limit_applied_at"),
    }
    profile.updated_at = now

    db.add(
        TrustEvents(
            user_id=user_id,
            source_type="recompute",
            source_id=None,
            score_delta=score - previous_score,
            reason_code="profile_recomputed",
            metadata_={"trust_level": level},
        )
    )
    if auto_limit_applied:
        db.add(
            TrustEvents(
                user_id=user_id,
                source_type="limits",
                source_id=None,
                score_delta=0,
                reason_code="trust_limit_uplift_applied",
                metadata_={
                    "daily_limit_before": str(current_daily_limit),
                    "daily_limit_after": str(next_daily_limit),
                    "monthly_limit_before": str(current_monthly_limit),
                    "monthly_limit_after": str(next_monthly_limit),
                    "limit_multiplier": str(limit_multiplier),
                },
            )
        )

    await _set_badge(db, user_id=user_id, badge_code="kyc_verified", enabled=kyc_verified)
    await _set_badge(
        db,
        user_id=user_id,
        badge_code="reliable_payer",
        enabled=successful_payment_requests >= 3 and dispute_count == 0,
    )
    await _set_badge(db, user_id=user_id, badge_code="seasoned_user", enabled=account_age_days >= 180)

    await db.commit()
    await db.refresh(profile)
    await db.refresh(user)
    return await _serialize_profile(db, profile, user=user)


async def get_trust_profile(db: AsyncSession, *, user_id: UUID) -> dict:
    profile = await db.scalar(select(TrustProfiles).where(TrustProfiles.user_id == user_id))
    profile_missing = profile is None
    profile_stale = False
    if profile and profile.last_computed_at:
        computed_at = profile.last_computed_at
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        profile_stale = computed_at < (_utcnow() - TRUST_PROFILE_STALE_AFTER)
    elif profile:
        profile_stale = True

    if profile_missing or profile_stale:
        recomputed_profile = await recompute_trust_profile(db, user_id=user_id)
        events = (
            await db.execute(
                select(TrustEvents).where(TrustEvents.user_id == user_id).order_by(TrustEvents.created_at.desc()).limit(20)
            )
        ).scalars().all()
        return {"profile": recomputed_profile, "events": events}

    events = (
        await db.execute(
            select(TrustEvents).where(TrustEvents.user_id == user_id).order_by(TrustEvents.created_at.desc()).limit(20)
        )
    ).scalars().all()
    return {"profile": await _serialize_profile(db, profile), "events": events}
