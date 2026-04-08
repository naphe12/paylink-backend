from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ScheduledExternalTransferPayload(BaseModel):
    partner_name: str = Field(min_length=2, max_length=80)
    country_destination: str = Field(min_length=1, max_length=120)
    recipient_name: str = Field(min_length=2, max_length=120)
    recipient_phone: str = Field(min_length=8, max_length=20)
    recipient_email: EmailStr | None = None


class ScheduledTransferCreate(BaseModel):
    transfer_type: Literal["internal", "external"] = "internal"
    receiver_identifier: str | None = None
    amount: Decimal = Field(gt=0)
    frequency: Literal["daily", "weekly", "monthly"]
    next_run_at: datetime
    note: str | None = None
    remaining_runs: int | None = Field(default=None, ge=1)
    max_consecutive_failures: int = Field(default=3, ge=1, le=10)
    external_transfer: ScheduledExternalTransferPayload | None = None

    @model_validator(mode="after")
    def validate_transfer_target(self):
        if self.transfer_type == "internal":
            if not str(self.receiver_identifier or "").strip():
                raise ValueError("receiver_identifier requis pour un transfert interne")
        elif self.external_transfer is None:
            raise ValueError("external_transfer requis pour un transfert externe")
        return self


class ScheduledTransferRead(BaseModel):
    schedule_id: UUID
    user_id: UUID
    receiver_user_id: UUID | None = None
    receiver_identifier: str
    transfer_type: Literal["internal", "external"] = "internal"
    external_transfer: ScheduledExternalTransferPayload | None = None
    amount: Decimal
    currency_code: str
    frequency: str
    status: str
    note: str | None = None
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_result: str | None = None
    remaining_runs: int | None = None
    failure_count: int = 0
    max_consecutive_failures: int = 3
    auto_paused_for_failures: bool = False
    is_due: bool = False
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
