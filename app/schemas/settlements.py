

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.provideraccounts import ProviderAccountsRead

class SettlementsBase(BaseModel):
    settlement_id: str
    currency_code: str
    amount: decimal.Decimal
    status: str
    provider_account_id: Optional[str]
    scheduled_at: Optional[datetime]
    executed_at: Optional[datetime]

class SettlementsCreate(SettlementsBase):
    settlement_id: str
    currency_code: str
    amount: decimal.Decimal
    status: str
    provider_account_id: Optional[str]
    scheduled_at: Optional[datetime]
    executed_at: Optional[datetime]

class SettlementsUpdate(BaseModel):
    settlement_id: Optional[str]
    currency_code: Optional[str]
    amount: Optional[decimal.Decimal]
    status: Optional[str]
    provider_account_id: Optional[Optional[str]]
    scheduled_at: Optional[Optional[datetime]]
    executed_at: Optional[Optional[datetime]]

class SettlementsRead(SettlementsBase):
    settlement_id: str
    currency_code: str
    amount: decimal.Decimal
    status: str
    provider_account_id: Optional[str]
    scheduled_at: Optional[datetime]
    executed_at: Optional[datetime]
    currencies: Optional["CurrenciesRead"] = None
    provider_account: Optional["ProviderAccountsRead"] = None
    class Config:
        from_attributes = True
