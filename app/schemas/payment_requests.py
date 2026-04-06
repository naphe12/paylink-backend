from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class PaymentRequestAction(BaseModel):
    reason: str | None = None


class PaymentRequestEventRead(BaseModel):
    event_id: UUID
    actor_user_id: UUID | None = None
    actor_role: str | None = None
    event_type: str
    before_status: str | None = None
    after_status: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
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
    due_at: datetime | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    declined_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_reminder_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    counterpart_label: str | None = None
    role: str | None = None
    is_due: bool = False

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaymentRequestDetailRead(BaseModel):
    request: PaymentRequestRead
    events: list[PaymentRequestEventRead] = Field(default_factory=list)


class PaymentRequestBatchRunRead(BaseModel):
    reminded_count: int = 0
    expired_count: int = 0
    processed_requests: list[PaymentRequestRead] = Field(default_factory=list)


class PaymentRequestAdminRead(PaymentRequestRead):
    requester_label: str | None = None
    payer_label: str | None = None


class PaymentRequestAdminDetailRead(BaseModel):
    request: PaymentRequestAdminRead
    events: list[PaymentRequestEventRead] = Field(default_factory=list)
