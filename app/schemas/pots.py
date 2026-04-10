from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PotCreate(BaseModel):
    title: str
    target_amount: Decimal = Field(gt=0)
    deadline_at: datetime | None = None
    description: str | None = None
    is_public: bool = False
    pot_mode: str = "collection"


class PotMemberCreate(BaseModel):
    identifier: str
    target_amount: Decimal | None = Field(default=None, gt=0)


class PotMemberUpdate(BaseModel):
    target_amount: Decimal | None = Field(default=None, gt=0)
    status: str | None = None


class PotMemberRead(BaseModel):
    membership_id: UUID
    pot_id: UUID
    user_id: UUID
    role: str
    status: str
    target_amount: Decimal | None = None
    contributed_amount: Decimal = Decimal("0")
    remaining_amount: Decimal | None = None
    progress_percent: float = 0
    member_label: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PotContributionCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    note: str | None = None


class PotContributionRead(BaseModel):
    contribution_id: UUID
    pot_id: UUID
    user_id: UUID
    amount: Decimal
    currency_code: str
    note: str | None = None
    source: str
    contributor_label: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PotRead(BaseModel):
    pot_id: UUID
    owner_user_id: UUID
    title: str
    description: str | None = None
    currency_code: str
    target_amount: Decimal
    current_amount: Decimal
    share_token: str | None = None
    is_public: bool = False
    deadline_at: datetime | None = None
    status: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    progress_percent: float = 0
    remaining_amount: Decimal = Decimal("0")
    days_remaining: int | None = None
    deadline_passed: bool = False
    recommended_daily_contribution: Decimal | None = None
    recommended_per_member_contribution: Decimal | None = None
    can_contribute: bool = True
    contribution_block_reason: str | None = None
    pot_mode: str = "collection"
    access_role: str = "owner"
    members: list[PotMemberRead] = Field(default_factory=list)
    contributions: list[PotContributionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
