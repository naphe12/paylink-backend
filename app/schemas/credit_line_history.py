from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreditLineHistoryBase(BaseModel):
    entry_id: UUID
    user_id: UUID
    transaction_id: UUID | None = None
    amount: Decimal
    credit_available_before: Decimal
    credit_available_after: Decimal
    description: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CreditLineHistoryCreate(BaseModel):
    user_id: UUID
    transaction_id: UUID | None = None
    amount: Decimal
    credit_available_before: Decimal
    credit_available_after: Decimal
    description: str | None = None


class CreditLineHistoryRead(CreditLineHistoryBase):
    pass
