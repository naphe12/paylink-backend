from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VirtualCardCreate(BaseModel):
    cardholder_name: str | None = None
    card_type: str = "standard"
    spending_limit: Decimal = Field(ge=0, default=Decimal("0"))
    daily_limit: Decimal = Field(ge=0, default=Decimal("0"))
    monthly_limit: Decimal = Field(ge=0, default=Decimal("0"))
    blocked_categories: list[str] = Field(default_factory=list)


class VirtualCardChargeCreate(BaseModel):
    merchant_name: str
    merchant_category: str | None = None
    amount: Decimal = Field(gt=0)


class VirtualCardStatusUpdate(BaseModel):
    status: str


class VirtualCardControlsUpdate(BaseModel):
    daily_limit: Decimal = Field(ge=0, default=Decimal("0"))
    monthly_limit: Decimal = Field(ge=0, default=Decimal("0"))
    blocked_categories: list[str] = Field(default_factory=list)


class VirtualCardTransactionRead(BaseModel):
    card_tx_id: UUID
    card_id: UUID
    user_id: UUID
    merchant_name: str
    merchant_category: str | None = None
    amount: Decimal
    currency_code: str
    status: str
    decline_reason: str | None = None
    reference: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class VirtualCardRead(BaseModel):
    card_id: UUID
    user_id: UUID
    linked_wallet_id: UUID | None = None
    cardholder_name: str
    brand: str
    card_type: str
    currency_code: str
    masked_pan: str
    last4: str
    exp_month: int
    exp_year: int
    spending_limit: Decimal
    spent_amount: Decimal
    daily_limit: Decimal = Decimal("0")
    monthly_limit: Decimal = Decimal("0")
    blocked_categories: list[str] = Field(default_factory=list)
    daily_spent: Decimal = Decimal("0")
    monthly_spent: Decimal = Decimal("0")
    daily_remaining: Decimal | None = None
    monthly_remaining: Decimal | None = None
    last_decline_reason: str | None = None
    status: str
    frozen_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_used_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    plain_pan: str | None = None
    plain_cvv: str | None = None
    transactions: list[VirtualCardTransactionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class VirtualCardAdminRead(VirtualCardRead):
    user_label: str
    user_email: str | None = None
    user_paytag: str | None = None
    user_role: str | None = None
    transaction_count: int = 0
    declined_count: int = 0
    utilization_percent: float = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
