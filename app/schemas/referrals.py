from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReferralRewardRead(BaseModel):
    reward_id: UUID
    referrer_user_id: UUID
    referred_user_id: UUID
    status: str
    activation_reason: str | None = None
    amount: Decimal
    currency_code: str
    credited: bool
    activated_at: datetime | None = None
    credited_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ReferralProfileRead(BaseModel):
    user_id: UUID
    referral_code: str
    total_referrals: int
    activated_referrals: int
    rewards_earned: Decimal
    currency_code: str
    referral_link: str
    pending_rewards: int
    rewards: list[ReferralRewardRead] = Field(default_factory=list)


class ReferralApplyCode(BaseModel):
    referral_code: str
