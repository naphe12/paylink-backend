from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral_profiles import ReferralProfiles
from app.models.referral_rewards import ReferralRewards
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions

DEFAULT_REFERRAL_REWARD = Decimal("2500")
MIN_QUALIFIED_ACTIVITY_AMOUNT = Decimal("100")


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


async def _compute_activation_signals(db: AsyncSession, *, user_id: UUID) -> dict:
    successful_tx_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Transactions)
            .where(
                Transactions.initiated_by == user_id,
                Transactions.status.in_(("succeeded", "completed")),
            )
        )
        or 0
    )
    qualified_tx_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Transactions)
            .where(
                Transactions.initiated_by == user_id,
                Transactions.status.in_(("succeeded", "completed")),
                Transactions.amount >= MIN_QUALIFIED_ACTIVITY_AMOUNT,
            )
        )
        or 0
    )
    wallet_activity_count = int(
        await db.scalar(
            select(func.count())
            .select_from(WalletTransactions)
            .where(
                WalletTransactions.user_id == user_id,
                WalletTransactions.amount > 0,
            )
        )
        or 0
    )
    wallet_activity_types = int(
        await db.scalar(
            select(func.count(func.distinct(func.lower(func.coalesce(WalletTransactions.operation_type, "")))))
            .where(
                WalletTransactions.user_id == user_id,
                WalletTransactions.amount > 0,
            )
        )
        or 0
    )

    has_qualified_transaction = qualified_tx_count >= 1
    has_diverse_wallet_activity = wallet_activity_count >= 2 and wallet_activity_types >= 2
    progress_percent = round(
        min(
            (60 if has_qualified_transaction else 0) + (40 if has_diverse_wallet_activity else 0),
            100,
        ),
        2,
    )
    next_step = None
    if not has_qualified_transaction:
        next_step = "Effectuer une premiere transaction reussie d'au moins 100 BIF."
    elif not has_diverse_wallet_activity:
        next_step = "Realiser encore une operation wallet d'un type different pour valider l'activation."

    return {
        "qualified_transaction": has_qualified_transaction,
        "diverse_wallet_activity": has_diverse_wallet_activity,
        "successful_tx_count": successful_tx_count,
        "qualified_tx_count": qualified_tx_count,
        "wallet_activity_count": wallet_activity_count,
        "wallet_activity_types": wallet_activity_types,
        "progress_percent": progress_percent,
        "is_ready": has_qualified_transaction and has_diverse_wallet_activity,
        "next_step": next_step,
    }


async def get_my_referral_profile(db: AsyncSession, *, current_user: Users) -> dict:
    profile = await ensure_referral_profile(db, user=current_user)
    rewards_rows = (
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
    pending_rewards = sum(1 for reward in rewards_rows if reward.status == "pending")
    activated_referrals = sum(1 for reward in rewards_rows if reward.status == "activated")
    profile.total_referrals = int(total_referrals or 0)
    profile.activated_referrals = int(activated_referrals)
    profile.rewards_earned = sum((Decimal(str(reward.amount or 0)) for reward in rewards_rows if reward.credited), Decimal("0"))
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()

    my_pending_reward = await db.scalar(
        select(ReferralRewards).where(
            ReferralRewards.referred_user_id == current_user.user_id,
            ReferralRewards.status == "pending",
        )
    )
    my_activation_signals = (
        await _compute_activation_signals(db, user_id=current_user.user_id)
        if my_pending_reward
        else {
            "progress_percent": 0,
            "is_ready": False,
            "next_step": None,
        }
    )
    serialized_rewards = []
    for reward in rewards_rows:
        reward_metadata = dict(reward.metadata_ or {})
        reward_progress = reward_metadata.get("activation_progress_percent")
        if reward.status == "activated":
            reward_progress = 100
        serialized_rewards.append(
            {
                "reward_id": reward.reward_id,
                "referrer_user_id": reward.referrer_user_id,
                "referred_user_id": reward.referred_user_id,
                "status": reward.status,
                "activation_reason": reward.activation_reason,
                "amount": Decimal(str(reward.amount or 0)),
                "currency_code": reward.currency_code,
                "credited": bool(reward.credited),
                "activation_progress_percent": float(reward_progress or 0),
                "activated_at": reward.activated_at,
                "credited_at": reward.credited_at,
                "metadata": reward_metadata,
                "created_at": reward.created_at,
            }
        )
    activation_rate_percent = round(
        (Decimal(profile.activated_referrals) / Decimal(profile.total_referrals) * Decimal("100"))
        if profile.total_referrals > 0
        else Decimal("0"),
        2,
    )

    return {
        "user_id": profile.user_id,
        "referral_code": profile.referral_code,
        "total_referrals": profile.total_referrals,
        "activated_referrals": profile.activated_referrals,
        "rewards_earned": profile.rewards_earned,
        "currency_code": profile.currency_code,
        "referral_link": f"https://app.pesapaid.com/signup?ref={profile.referral_code}",
        "pending_rewards": pending_rewards,
        "activation_rate_percent": float(activation_rate_percent),
        "my_activation_progress_percent": float(my_activation_signals["progress_percent"]),
        "my_activation_ready": bool(my_activation_signals["is_ready"]),
        "my_activation_next_step": my_activation_signals["next_step"],
        "targeted_bonus_policy": "real-activity-only",
        "rewards": serialized_rewards,
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

    signals = await _compute_activation_signals(db, user_id=current_user.user_id)
    reward_metadata = dict(reward.metadata_ or {})
    reward_metadata["activation_progress_percent"] = signals["progress_percent"]
    reward_metadata["activation_checks"] = {
        "qualified_transaction": signals["qualified_transaction"],
        "diverse_wallet_activity": signals["diverse_wallet_activity"],
        "successful_tx_count": signals["successful_tx_count"],
        "qualified_tx_count": signals["qualified_tx_count"],
        "wallet_activity_count": signals["wallet_activity_count"],
        "wallet_activity_types": signals["wallet_activity_types"],
    }
    reward.metadata_ = reward_metadata
    if not signals["is_ready"]:
        await db.commit()
        return {
            "status": "pending",
            "reward_id": str(reward.reward_id),
            "progress_percent": float(signals["progress_percent"]),
            "next_step": signals["next_step"],
        }

    reward.status = "activated"
    reward.activation_reason = "qualified_real_activity"
    reward.activated_at = datetime.now(timezone.utc)
    reward.credited = True
    reward.credited_at = reward.activated_at
    reward_metadata["activation_progress_percent"] = 100
    reward_metadata["activation_completed_at"] = reward.activated_at.isoformat()
    reward.metadata_ = reward_metadata
    await db.commit()
    return {
        "status": "activated",
        "reward_id": str(reward.reward_id),
        "amount": str(reward.amount),
        "currency_code": reward.currency_code,
    }
