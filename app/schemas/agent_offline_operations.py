from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentOfflineOperationCreate(BaseModel):
    client_user_id: UUID
    operation_type: str
    amount: Decimal = Field(gt=0)
    note: str | None = None


class AgentOfflineOperationRead(BaseModel):
    operation_id: UUID
    agent_user_id: UUID
    agent_id: UUID
    client_user_id: UUID
    client_label: str
    operation_type: str
    amount: Decimal
    currency_code: str
    note: str | None = None
    offline_reference: str
    status: str
    failure_reason: str | None = None
    conflict_reason: str | None = None
    conflict_reason_label: str | None = None
    requires_review: bool = False
    is_stale: bool = False
    queued_age_minutes: int = 0
    snapshot_available: Decimal | None = None
    current_available: Decimal | None = None
    balance_delta: Decimal | None = None
    synced_response: dict[str, Any] | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    queued_at: datetime
    synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AgentOfflineOperationAdminRead(AgentOfflineOperationRead):
    agent_label: str
    agent_email: str | None = None
    agent_phone_e164: str | None = None
    client_email: str | None = None
    client_phone_e164: str | None = None
    client_paytag: str | None = None


class AgentOfflineSyncSummary(BaseModel):
    synced: int
    failed: int
    operations: list[AgentOfflineOperationRead] = Field(default_factory=list)
