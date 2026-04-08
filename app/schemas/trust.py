from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrustBadgeRead(BaseModel):
    badge_code: str
    name: str
    description: str
    granted_at: datetime | None = None


class TrustEventRead(BaseModel):
    event_id: UUID
    user_id: UUID
    source_type: str
    source_id: str | None = None
    score_delta: int
    reason_code: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TrustProfileRead(BaseModel):
    user_id: UUID
    trust_score: int
    trust_level: str
    kyc_tier: int | None = None
    successful_payment_requests: int
    total_payment_requests: int = 0
    payment_request_success_rate: Decimal | None = None
    successful_p2p_trades: int
    total_p2p_trades: int = 0
    p2p_completion_rate: Decimal | None = None
    p2p_dispute_count: int = 0
    open_p2p_dispute_count: int = 0
    p2p_dispute_rate: Decimal | None = None
    dispute_count: int
    failed_obligation_count: int
    chargeback_like_count: int
    kyc_verified: bool
    account_age_days: int
    current_daily_limit: Decimal | None = None
    current_monthly_limit: Decimal | None = None
    recommended_daily_limit: Decimal | None = None
    recommended_monthly_limit: Decimal | None = None
    limit_multiplier: Decimal | None = None
    limit_uplift_active: bool = False
    reputation_tier: str = "watch"
    reputation_note: str | None = None
    auto_limit_applied_at: datetime | None = None
    last_computed_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    badges: list[TrustBadgeRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TrustProfileDetailRead(BaseModel):
    profile: TrustProfileRead
    events: list[TrustEventRead] = Field(default_factory=list)
