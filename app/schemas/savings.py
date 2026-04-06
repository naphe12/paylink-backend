from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SavingsGoalCreate(BaseModel):
    title: str
    target_amount: Decimal = Field(gt=0)
    target_date: datetime | None = None
    note: str | None = None
    locked: bool = False


class SavingsGoalMovementCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    note: str | None = None


class SavingsRoundUpRuleUpdate(BaseModel):
    enabled: bool = True
    increment: Decimal = Field(gt=0)
    max_amount: Decimal | None = Field(default=None, gt=0)


class SavingsRoundUpApplyCreate(BaseModel):
    spent_amount: Decimal = Field(gt=0)
    note: str | None = None


class SavingsAutoContributionRuleUpdate(BaseModel):
    enabled: bool = True
    amount: Decimal = Field(gt=0)
    frequency: str
    next_run_at: datetime


class SavingsAutoContributionRunCreate(BaseModel):
    note: str | None = None


class SavingsRoundUpRuleRead(BaseModel):
    enabled: bool = False
    increment: Decimal | None = None
    max_amount: Decimal | None = None
    last_applied_at: datetime | None = None
    updated_at: datetime | None = None


class SavingsAutoContributionRuleRead(BaseModel):
    enabled: bool = False
    amount: Decimal | None = None
    frequency: str | None = None
    next_run_at: datetime | None = None
    last_applied_at: datetime | None = None
    updated_at: datetime | None = None
    is_due: bool = False


class SavingsMovementRead(BaseModel):
    movement_id: UUID
    goal_id: UUID
    user_id: UUID
    amount: Decimal
    currency_code: str
    direction: str
    source: str
    note: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SavingsGoalRead(BaseModel):
    goal_id: UUID
    user_id: UUID
    title: str
    note: str | None = None
    currency_code: str
    target_amount: Decimal
    current_amount: Decimal
    locked: bool
    target_date: datetime | None = None
    status: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    progress_percent: float = 0
    remaining_amount: Decimal = Decimal("0")
    round_up_rule: SavingsRoundUpRuleRead = Field(default_factory=SavingsRoundUpRuleRead)
    auto_contribution_rule: SavingsAutoContributionRuleRead = Field(default_factory=SavingsAutoContributionRuleRead)
    movements: list[SavingsMovementRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
