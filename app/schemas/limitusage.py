# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

#


if TYPE_CHECKING:
    from app.schemas.limits import LimitsRead
    from app.schemas.users import UsersRead

class LimitUsageBase(BaseModel):
    usage_id: str
    user_id: str
    limit_id: str
    period_start: datetime
    tx_count: int
    total_amount: decimal.Decimal

class LimitUsageCreate(LimitUsageBase):
    usage_id: str
    user_id: str
    limit_id: str
    period_start: datetime
    tx_count: int
    total_amount: decimal.Decimal

class LimitUsageUpdate(BaseModel):
    usage_id: Optional[str]
    user_id: Optional[str]
    limit_id: Optional[str]
    period_start: Optional[datetime]
    tx_count: Optional[int]
    total_amount: Optional[decimal.Decimal]

class LimitUsageRead(LimitUsageBase):
    usage_id: str
    user_id: str
    limit_id: str
    period_start: datetime
    tx_count: int
    total_amount: decimal.Decimal
    limit: Optional["LimitsRead"] = None  # ✅ référence indirecte
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
