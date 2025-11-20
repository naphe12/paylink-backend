# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.providers import ProvidersRead


class FxRatesBase(BaseModel):
    fx_id: int
    base_currency: str
    quote_currency: str
    rate: decimal.Decimal
    obtained_at: datetime
    provider_id: Optional[str]

class FxRatesCreate(FxRatesBase):
    fx_id: int
    base_currency: str
    quote_currency: str
    rate: decimal.Decimal
    obtained_at: datetime
    provider_id: Optional[str]

class FxRatesUpdate(BaseModel):
    fx_id: Optional[int]
    base_currency: Optional[str]
    quote_currency: Optional[str]
    rate: Optional[decimal.Decimal]
    obtained_at: Optional[datetime]
    provider_id: Optional[Optional[str]]

class FxRatesRead(FxRatesBase):
    fx_id: int
    base_currency: str
    quote_currency: str
    rate: decimal.Decimal
    obtained_at: datetime
    provider_id: Optional[str]    
    provider: Optional["ProvidersRead"] = None
    base_currency: Optional["CurrenciesRead"] = None
    target_currency: Optional["CurrenciesRead"] = None
    class Config:
        from_attributes = True
