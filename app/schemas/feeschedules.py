# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

#



if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.providers import ProvidersRead
   

class FeeSchedulesBase(BaseModel):
    fee_id: str
    name: str
    active: bool
    created_at: datetime
    channel: Optional[str]
    provider_id: Optional[str]
    country_code: Optional[str]
    currency_code: Optional[str]
    min_amount: Optional[decimal.Decimal]
    max_amount: Optional[decimal.Decimal]
    fixed_fee: Optional[decimal.Decimal]
    percent_fee: Optional[decimal.Decimal]

class FeeSchedulesCreate(FeeSchedulesBase):
    fee_id: str
    name: str
    active: bool
    channel: Optional[str]
    provider_id: Optional[str]
    country_code: Optional[str]
    currency_code: Optional[str]
    min_amount: Optional[decimal.Decimal]
    max_amount: Optional[decimal.Decimal]
    fixed_fee: Optional[decimal.Decimal]
    percent_fee: Optional[decimal.Decimal]

class FeeSchedulesUpdate(BaseModel):
    fee_id: Optional[str]
    name: Optional[str]
    active: Optional[bool]
    created_at: Optional[datetime]
    channel: Optional[Optional[str]]
    provider_id: Optional[Optional[str]]
    country_code: Optional[Optional[str]]
    currency_code: Optional[Optional[str]]
    min_amount: Optional[Optional[decimal.Decimal]]
    max_amount: Optional[Optional[decimal.Decimal]]
    fixed_fee: Optional[Optional[decimal.Decimal]]
    percent_fee: Optional[Optional[decimal.Decimal]]

class FeeSchedulesRead(FeeSchedulesBase):
    fee_id: str
    name: str
    active: bool
    created_at: datetime
    channel: Optional[str]
    provider_id: Optional[str]
    country_code: Optional[str]
    currency_code: Optional[str]
    min_amount: Optional[decimal.Decimal]
    max_amount: Optional[decimal.Decimal]
    fixed_fee: Optional[decimal.Decimal]
    percent_fee: Optional[decimal.Decimal]
    currency: Optional["CurrenciesRead"] = None  # ✅ forward reference
    provider: Optional["ProvidersRead"] = None
    class Config:
        from_attributes = True
