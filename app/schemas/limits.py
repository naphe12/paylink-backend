# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
#
#
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.limitusage import LimitUsageRead
    from app.schemas.currencies import CurrenciesRead

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.limitusage import LimitUsageRead

class LimitsBase(BaseModel):
    limit_id: str
    name: str
    period: str
    created_at: datetime
    kyc_level: Optional[str]
    currency_code: Optional[str]
    max_tx_amount: Optional[decimal.Decimal]
    max_tx_count: Optional[int]
    max_total_amount: Optional[decimal.Decimal]

class LimitsCreate(LimitsBase):
    limit_id: str
    name: str
    period: str
    kyc_level: Optional[str]
    currency_code: Optional[str]
    max_tx_amount: Optional[decimal.Decimal]
    max_tx_count: Optional[int]
    max_total_amount: Optional[decimal.Decimal]

class LimitsUpdate(BaseModel):
    limit_id: Optional[str]
    name: Optional[str]
    period: Optional[str]
    created_at: Optional[datetime]
    kyc_level: Optional[Optional[str]]
    currency_code: Optional[Optional[str]]
    max_tx_amount: Optional[Optional[decimal.Decimal]]
    max_tx_count: Optional[Optional[int]]
    max_total_amount: Optional[Optional[decimal.Decimal]]

class LimitsRead(LimitsBase):
    limit_id: str
    name: str
    period: str
    created_at: datetime
    kyc_level: Optional[str]
    currency_code: Optional[str]
    max_tx_amount: Optional[decimal.Decimal]
    max_tx_count: Optional[int]
    max_total_amount: Optional[decimal.Decimal]
    currency: Optional["CurrenciesRead"] = None
    usages: Optional[List["LimitUsageRead"]] = None  # ✅ référence indirecte
    class Config:
        from_attributes = True
