from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MerchantStoreCreate(BaseModel):
    code: str | None = None
    name: str
    country_code: str | None = None
    city: str | None = None
    address_line: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantTerminalCreate(BaseModel):
    label: str
    channel: str = "qr"
    device_fingerprint: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantOrderCreate(BaseModel):
    store_id: UUID | None = None
    terminal_id: UUID | None = None
    channel: str = "manual"
    merchant_reference: str | None = None
    external_reference: str | None = None
    amount: Decimal = Field(gt=0)
    currency_code: str
    customer_user_id: UUID | None = None
    customer_label: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    expires_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantOrderAction(BaseModel):
    reason: str | None = None


class MerchantPaymentLinkCreate(BaseModel):
    mode: str = "one_time"
    fixed_amount: Decimal | None = Field(default=None, gt=0)
    currency_code: str | None = None
    max_uses: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantStaticQrCreate(BaseModel):
    store_id: UUID | None = None
    terminal_id: UUID | None = None
    fixed_amount: Decimal | None = Field(default=None, gt=0)
    currency_code: str | None = None
    label: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantDynamicQrCreate(BaseModel):
    expires_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantWalletPaymentCreate(BaseModel):
    wallet_id: UUID | None = None
    note: str | None = None


class MerchantExternalPaymentIntentCreate(BaseModel):
    rail: str
    provider_code: str
    provider_channel: str | None = None
    payer_identifier: str | None = None
    return_url: HttpUrl | None = None
    cancel_url: HttpUrl | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantRefundCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    reason: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")


class MerchantRefundAdminAction(BaseModel):
    reason: str | None = None


class MerchantProfileStatusUpdate(BaseModel):
    status: str
    reason: str | None = None


class MerchantReceiptDispatchCreate(BaseModel):
    channel: str = "email"
    recipient: str | None = None


class MerchantProfileRead(BaseModel):
    merchant_id: UUID
    business_id: UUID
    public_name: str
    legal_name: str
    country_code: str | None = None
    settlement_wallet_id: UUID | None = None
    default_currency: str | None = None
    mcc: str | None = None
    support_email: str | None = None
    support_phone: str | None = None
    status: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantStoreRead(BaseModel):
    store_id: UUID
    merchant_id: UUID
    code: str | None = None
    name: str
    country_code: str | None = None
    city: str | None = None
    address_line: str | None = None
    status: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantTerminalRead(BaseModel):
    terminal_id: UUID
    store_id: UUID
    label: str
    channel: str
    status: str
    last_seen_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantOrderRead(BaseModel):
    order_id: UUID
    merchant_id: UUID
    store_id: UUID | None = None
    terminal_id: UUID | None = None
    channel: str
    merchant_reference: str
    external_reference: str | None = None
    amount: Decimal
    currency_code: str
    collected_amount: Decimal
    refunded_amount: Decimal
    customer_user_id: UUID | None = None
    customer_label: str | None = None
    description: str | None = None
    status: str
    due_at: datetime | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantQrCodeRead(BaseModel):
    qr_id: UUID
    merchant_id: UUID
    order_id: UUID | None = None
    qr_type: str
    token: str
    status: str
    fixed_amount: Decimal | None = None
    currency_code: str | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MerchantPaymentLinkRead(BaseModel):
    link_id: UUID
    merchant_id: UUID
    order_id: UUID | None = None
    token: str
    mode: str
    status: str
    fixed_amount: Decimal | None = None
    currency_code: str | None = None
    max_uses: int | None = None
    use_count: int = 0
    expires_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MerchantPaymentAttemptRead(BaseModel):
    attempt_id: UUID
    order_id: UUID
    payer_user_id: UUID | None = None
    payer_wallet_id: UUID | None = None
    rail: str
    status: str
    amount: Decimal
    currency_code: str
    payment_intent_id: UUID | None = None
    wallet_tx_id: UUID | None = None
    provider_reference: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    authorized_at: datetime | None = None
    settled_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantRefundRead(BaseModel):
    refund_id: UUID
    merchant_id: UUID
    order_id: UUID
    attempt_id: UUID | None = None
    amount: Decimal
    currency_code: str
    reason: str | None = None
    status: str
    refund_tx_id: UUID | None = None
    provider_reference: str | None = None
    completed_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantReceiptRead(BaseModel):
    receipt_id: UUID
    order_id: UUID
    receipt_number: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime
    voided_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MerchantOrderStatusRead(BaseModel):
    order_id: UUID
    status: str
    collected_amount: Decimal
    refunded_amount: Decimal
    paid_at: datetime | None = None
    last_attempt: MerchantPaymentAttemptRead | None = None


class MerchantOrderDetailRead(BaseModel):
    order: MerchantOrderRead
    attempts: list[MerchantPaymentAttemptRead] = Field(default_factory=list)
    refunds: list[MerchantRefundRead] = Field(default_factory=list)
    receipt: MerchantReceiptRead | None = None


class MerchantCheckoutSessionRead(BaseModel):
    merchant_id: UUID
    merchant_label: str
    order: MerchantOrderRead | None = None
    payment_link: MerchantPaymentLinkRead | None = None
    qr_code: MerchantQrCodeRead | None = None
    available_rails: list[str] = Field(default_factory=list)
    can_pay_with_wallet: bool = False


class MerchantExternalPaymentIntentRead(BaseModel):
    order: MerchantOrderRead
    attempt: MerchantPaymentAttemptRead
    payment_intent: dict[str, Any]


class MerchantOverviewRead(BaseModel):
    business_id: UUID
    merchant_id: UUID
    total_orders: int = 0
    paid_orders: int = 0
    pending_orders: int = 0
    total_paid_amount: Decimal = Decimal("0")
    total_refunded_amount: Decimal = Decimal("0")
    active_stores: int = 0
    active_terminals: int = 0


class MerchantEventRead(BaseModel):
    event_id: UUID
    merchant_id: UUID
    order_id: UUID | None = None
    attempt_id: UUID | None = None
    refund_id: UUID | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
