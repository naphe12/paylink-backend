from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral_profiles import ReferralProfiles
from app.models.referral_rewards import ReferralRewards
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions

DEFAULT_REFERRAL_REWARD = Decimal("2500")


def _build_referral_code(user: Users) -> str:
    base = str(getattr(user, "paytag", None) or getattr(user, "username", None) or getattr(user, "full_name", "USER"))
    token = "".join(ch for ch in base.upper() if ch.isalnum())[:6] or "PESA"
    suffix = str(user.user_id).replace("-", "").upper()[:6]
    return f"{token}{suffix}"


async def ensure_referral_profile(db: AsyncSession, *, user: Users) -> ReferralProfiles:
    profile = await db.get(ReferralProfiles, user.user_id)
    if profile is not None:
        return profile

    referral_code = _build_referral_code(user)
    collision_idx = 1
    while await db.scalar(select(ReferralProfiles).where(ReferralProfiles.referral_code == referral_code)):
        collision_idx += 1
        referral_code = f"{_build_referral_code(user)}{collision_idx}"

    profile = ReferralProfiles(
        user_id=user.user_id,
        referral_code=referral_code,
        total_referrals=0,
        activated_referrals=0,
        rewards_earned=Decimal("0"),
        currency_code="BIF",
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_my_referral_profile(db: AsyncSession, *, current_user: Users) -> dict:
    profile = await ensure_referral_profile(db, user=current_user)
    rewards = (
        await db.execute(
            select(ReferralRewards)
            .where(ReferralRewards.referrer_user_id == current_user.user_id)
            .order_by(ReferralRewards.created_at.desc())
        )
    ).scalars().all()
    total_referrals = await db.scalar(
        select(func.count())
        .select_from(Users)
        .where(Users.referred_by == current_user.user_id)
    )
    pending_rewards = sum(1 for reward in rewards if reward.status == "pending")
    activated_referrals = sum(1 for reward in rewards if reward.status == "activated")
    profile.total_referrals = int(total_referrals or 0)
    profile.activated_referrals = int(activated_referrals)
    profile.rewards_earned = sum((Decimal(str(reward.amount or 0)) for reward in rewards if reward.credited), Decimal("0"))
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "user_id": profile.user_id,
        "referral_code": profile.referral_code,
        "total_referrals": profile.total_referrals,
        "activated_referrals": profile.activated_referrals,
        "rewards_earned": profile.rewards_earned,
        "currency_code": profile.currency_code,
        "referral_link": f"https://app.pesapaid.com/signup?ref={profile.referral_code}",
        "pending_rewards": pending_rewards,
        "rewards": rewards,
    }


async def apply_referral_code(db: AsyncSession, *, current_user: Users, referral_code: str) -> dict:
    code = str(referral_code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code de parrainage manquant")

    profile = await db.scalar(select(ReferralProfiles).where(ReferralProfiles.referral_code == code))
    if not profile:
        raise HTTPException(status_code=404, detail="Code de parrainage introuvable")
    if profile.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas utiliser votre propre code")
    if current_user.referred_by:
        raise HTTPException(status_code=400, detail="Un parrain est deja associe a ce compte")

    current_user.referred_by = profile.user_id
    reward = ReferralRewards(
        referrer_user_id=profile.user_id,
        referred_user_id=current_user.user_id,
        status="pending",
        amount=DEFAULT_REFERRAL_REWARD,
        currency_code="BIF",
    )
    db.add(reward)
    await db.commit()
    return {"status": "linked", "referrer_user_id": str(profile.user_id)}


async def activate_referral_if_eligible(db: AsyncSession, *, current_user: Users) -> dict | None:
    if not current_user.referred_by:
        return None
    reward = await db.scalar(
        select(ReferralRewards).where(
            ReferralRewards.referred_user_id == current_user.user_id,
            ReferralRewards.status == "pending",
        )
    )
    if not reward:
        return None

    successful_tx = await db.scalar(
        select(Transactions)
        .where(
            Transactions.initiated_by == current_user.user_id,
            Transactions.status.in_(("succeeded", "completed")),
        )
        .limit(1)
    )
    wallet_move = await db.scalar(
        select(WalletTransactions)
        .where(
            WalletTransactions.user_id == current_user.user_id,
            or_(
                WalletTransactions.operation_type.ilike("%transfer%"),
                WalletTransactions.operation_type.ilike("%payment%"),
                WalletTransactions.operation_type.ilike("%deposit%"),
            ),
        )
        .limit(1)
    )
    if not successful_tx and not wallet_move:
        raise HTTPException(status_code=400, detail="Aucune activation reelle detectee pour ce compte")

    reward.status = "activated"
    reward.activation_reason = "first_real_activity"
    reward.activated_at = datetime.now(timezone.utc)
    reward.credited = True
    reward.credited_at = reward.activated_at
    await db.commit()
    return {
        "status": "activated",
        "reward_id": str(reward.reward_id),
        "amount": str(reward.amount),
        "currency_code": reward.currency_code,
    }
