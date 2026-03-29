from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.operator_workflow import OperatorWorkflowRead


class MobileMoneyDepositIntentCreate(BaseModel):
    amount: Decimal
    currency_code: str = "BIF"
    provider_code: str = "lumicash_aggregator"
    provider_channel: str = "Lumicash"
    payer_identifier: str | None = None
    note: str | None = None


class PaymentIntentRead(BaseModel):
    intent_id: UUID
    direction: str
    rail: str
    status: str
    provider_code: str
    provider_channel: str | None = None
    amount: Decimal
    currency_code: str
    merchant_reference: str
    provider_reference: str | None = None
    payer_identifier: str | None = None
    target_instructions: dict[str, Any] = Field(default_factory=dict)
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    settled_at: datetime | None = None
    credited_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MobileMoneyWebhookPayload(BaseModel):
    event_id: str | None = None
    event_type: str | None = None
    merchant_reference: str | None = None
    provider_reference: str | None = None
    status: str
    amount: Decimal
    currency_code: str = "BIF"
    payer_identifier: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PaymentWebhookResult(BaseModel):
    ok: bool = True
    status: str
    merchant_reference: str
    credited: bool = False
    intent_id: UUID


class PaymentIntentUserLiteRead(BaseModel):
    user_id: UUID
    full_name: str | None = None
    email: str | None = None
    phone_e164: str | None = None


class PaymentIntentAdminRead(PaymentIntentRead):
    user: PaymentIntentUserLiteRead
    operator_workflow: OperatorWorkflowRead | None = None


class PaymentEventRead(BaseModel):
    event_id: UUID
    provider_code: str
    provider_event_type: str | None = None
    external_event_id: str | None = None
    provider_reference: str | None = None
    status: str | None = None
    reason_code: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentIntentAdminDetailRead(BaseModel):
    intent: PaymentIntentAdminRead
    events: list[PaymentEventRead] = Field(default_factory=list)


class PaymentIntentManualReconcileCreate(BaseModel):
    provider_reference: str | None = None
    note: str | None = None


class PaymentIntentAdminStatusActionCreate(BaseModel):
    action: str
    note: str | None = None
