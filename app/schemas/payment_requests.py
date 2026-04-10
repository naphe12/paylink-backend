from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class PaymentRequestCreate(BaseModel):
    payer_identifier: str | None = None
    amount: Decimal = Field(gt=0)
    currency_code: str
    title: str | None = None
    note: str | None = None
    merchant_reference: str | None = None
    due_at: datetime | None = None
    expires_at: datetime | None = None
    channel: str = "direct"
    recurrence_frequency: Literal["none", "daily", "weekly", "monthly"] = "none"
    recurrence_count: int | None = Field(default=None, ge=1, le=365)
    recurrence_end_at: datetime | None = None
    auto_pay_enabled: bool = False
    auto_pay_max_amount: Decimal | None = Field(default=None, gt=0)


class PaymentRequestAction(BaseModel):
    reason: str | None = None


class PaymentRequestAutoPayUpdate(BaseModel):
    enabled: bool
    max_amount: Decimal | None = Field(default=None, gt=0)
    reason: str | None = None


class PaymentRequestEventRead(BaseModel):
    event_id: UUID
    actor_user_id: UUID | None = None
    actor_role: str | None = None
    event_type: str
    before_status: str | None = None
    after_status: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("metadata_", "metadata"), serialization_alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaymentRequestRead(BaseModel):
    request_id: UUID
    requester_user_id: UUID
    payer_user_id: UUID | None = None
    amount: Decimal
    currency_code: str
    status: str
    channel: str
    title: str | None = None
    note: str | None = None
    share_token: str | None = None
    public_pay_url: str | None = None
    scan_to_pay_payload: dict[str, Any] = Field(default_factory=dict)
    due_at: datetime | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    declined_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_reminder_at: datetime | None = None
    manual_reminder_count: int = 0
    next_manual_reminder_at: datetime | None = None
    can_send_manual_reminder: bool = True
    metadata_: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("metadata_", "metadata"), serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
    counterpart_label: str | None = None
    role: str | None = None
    is_due: bool = False
    recurrence_frequency: Literal["none", "daily", "weekly", "monthly"] = "none"
    recurrence_count: int | None = None
    recurrence_end_at: datetime | None = None
    auto_pay_enabled: bool = False
    auto_pay_max_amount: Decimal | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaymentRequestDetailRead(BaseModel):
    request: PaymentRequestRead
    events: list[PaymentRequestEventRead] = Field(default_factory=list)


class PaymentRequestBatchRunRead(BaseModel):
    reminded_count: int = 0
    expired_count: int = 0
    auto_paid_count: int = 0
    processed_requests: list[PaymentRequestRead] = Field(default_factory=list)


class PaymentRequestAdminRead(PaymentRequestRead):
    requester_label: str | None = None
    payer_label: str | None = None


class PaymentRequestAdminDetailRead(BaseModel):
    request: PaymentRequestAdminRead
    events: list[PaymentRequestEventRead] = Field(default_factory=list)

