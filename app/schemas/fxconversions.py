# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

#



if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.transactions import TransactionsRead

class FxConversionsBase(BaseModel):
    conversion_id: str
    tx_id: str
    from_currency: str
    to_currency: str
    rate_used: decimal.Decimal
    fee_fx_bps: int
    created_at: datetime

class FxConversionsCreate(FxConversionsBase):
    conversion_id: str
    tx_id: str
    from_currency: str
    to_currency: str
    rate_used: decimal.Decimal
    fee_fx_bps: int

class FxConversionsUpdate(BaseModel):
    conversion_id: Optional[str]
    tx_id: Optional[str]
    from_currency: Optional[str]
    to_currency: Optional[str]
    rate_used: Optional[decimal.Decimal]
    fee_fx_bps: Optional[int]
    created_at: Optional[datetime]

class FxConversionsRead(FxConversionsBase):
    conversion_id: str
    tx_id: str
    from_currency: str
    to_currency: str
    rate_used: decimal.Decimal
    fee_fx_bps: int
    created_at: datetime
    base_currency: Optional["CurrenciesRead"] = None
    target_currency: Optional["CurrenciesRead"] = None
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
