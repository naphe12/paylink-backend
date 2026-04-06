from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessAccountCreate(BaseModel):
    legal_name: str
    display_name: str
    country_code: str | None = None


class BusinessMemberCreate(BaseModel):
    identifier: str
    role: str


class BusinessMemberUpdate(BaseModel):
    role: str | None = None
    status: str | None = None


class BusinessSubWalletCreate(BaseModel):
    label: str
    spending_limit: float = Field(ge=0)
    assigned_user_id: UUID | None = None


class BusinessSubWalletUpdate(BaseModel):
    label: str | None = None
    spending_limit: float | None = Field(default=None, ge=0)
    assigned_user_id: UUID | None = None
    status: str | None = None


class BusinessSubWalletMovementCreate(BaseModel):
    amount: float = Field(gt=0)
    note: str | None = None


class BusinessMemberRead(BaseModel):
    membership_id: UUID
    business_id: UUID
    user_id: UUID
    role: str
    status: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    member_label: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BusinessAccountRead(BaseModel):
    business_id: UUID
    owner_user_id: UUID
    legal_name: str
    display_name: str
    country_code: str | None = None
    is_active: bool
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    current_membership_role: str | None = None
    members: list[BusinessMemberRead] = Field(default_factory=list)
    sub_wallets: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
