from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScheduledTransferCreate(BaseModel):
    receiver_identifier: str
    amount: Decimal = Field(gt=0)
    frequency: str
    next_run_at: datetime
    note: str | None = None
    remaining_runs: int | None = Field(default=None, ge=1)


class ScheduledTransferRead(BaseModel):
    schedule_id: UUID
    user_id: UUID
    receiver_user_id: UUID | None = None
    receiver_identifier: str
    amount: Decimal
    currency_code: str
    frequency: str
    status: str
    note: str | None = None
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_result: str | None = None
    remaining_runs: int | None = None
    is_due: bool = False
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
