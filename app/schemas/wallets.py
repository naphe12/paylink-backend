

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    pass


class WalletsBase(BaseModel):
    wallet_id: str
    type: str
    currency_code: str
    available: decimal.Decimal
    pending: decimal.Decimal
    created_at: datetime
    updated_at: datetime
    user_id: Optional[str]

class WalletsCreate(WalletsBase):
    wallet_id: str
    type: str
    currency_code: str
    available: decimal.Decimal
    pending: decimal.Decimal
    user_id: Optional[str]

class WalletsUpdate(BaseModel):
    wallet_id: Optional[str]
    type: Optional[str]
    currency_code: Optional[str]
    available: Optional[decimal.Decimal]
    pending: Optional[decimal.Decimal]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    user_id: Optional[Optional[str]]

from decimal import Decimal
from uuid import UUID

# app/schemas/wallets.py
from pydantic import BaseModel


class WalletsRead(BaseModel):
    wallet_id: UUID
    user_id: UUID
    type: str
    currency_code: str
    available: Decimal
    pending: Decimal
    bonus_balance: Decimal | None = None
    display_currency_code: Optional[str] = None
    user_country_code: Optional[str] = None
    user_country_currency_code: Optional[str] = None

    class Config:
        from_attributes = True  # Pydantic v2


class WalletTopUp(BaseModel):
    amount: decimal.Decimal
