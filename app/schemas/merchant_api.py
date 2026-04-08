from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MerchantApiKeyCreate(BaseModel):
    key_name: str


class MerchantApiKeyRead(BaseModel):
    key_id: UUID
    business_id: UUID
    key_name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    plain_api_key: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantWebhookCreate(BaseModel):
    target_url: HttpUrl
    event_types: list[str] = Field(default_factory=list)
    max_consecutive_failures: int = Field(default=3, ge=1, le=10)


class MerchantWebhookStatusUpdate(BaseModel):
    status: str


class MerchantWebhookRead(BaseModel):
    webhook_id: UUID
    business_id: UUID
    target_url: str
    status: str
    event_types: list[str] = Field(default_factory=list)
    is_active: bool
    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    auto_paused_for_failures: bool = False
    last_tested_at: datetime | None = None
    revoked_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    plain_signing_secret: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantWebhookEventRead(BaseModel):
    event_id: UUID
    webhook_id: UUID
    business_id: UUID
    event_type: str
    delivery_status: str
    response_status_code: int | None = None
    request_signature: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    response_body: str | None = None
    attempt_count: int = 0
    last_attempted_at: datetime | None = None
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantIntegrationSummary(BaseModel):
    business_id: UUID
    business_label: str
    membership_role: str
    api_keys: list[MerchantApiKeyRead] = Field(default_factory=list)
    webhooks: list[MerchantWebhookRead] = Field(default_factory=list)
    recent_events: list[MerchantWebhookEventRead] = Field(default_factory=list)
