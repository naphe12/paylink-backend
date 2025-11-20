

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.tontines import TontinesRead
    from app.schemas.transactions import TransactionsRead
    from app.schemas.users import UsersRead


class TontinePayoutsBase(BaseModel):
    payout_id: str
    tontine_id: str
    beneficiary_id: str
    amount: decimal.Decimal
    tx_id: Optional[str]
    scheduled_at: Optional[datetime]
    paid_at: Optional[datetime]

class TontinePayoutsCreate(TontinePayoutsBase):
    payout_id: str
    tontine_id: str
    beneficiary_id: str
    amount: decimal.Decimal
    tx_id: Optional[str]
    scheduled_at: Optional[datetime]
    paid_at: Optional[datetime]

class TontinePayoutsUpdate(BaseModel):
    payout_id: Optional[str]
    tontine_id: Optional[str]
    beneficiary_id: Optional[str]
    amount: Optional[decimal.Decimal]
    tx_id: Optional[Optional[str]]
    scheduled_at: Optional[Optional[datetime]]
    paid_at: Optional[Optional[datetime]]

class TontinePayoutsRead(TontinePayoutsBase):
    payout_id: str
    tontine_id: str
    beneficiary_id: str
    amount: decimal.Decimal
    tx_id: Optional[str]
    scheduled_at: Optional[datetime]
    paid_at: Optional[datetime]
    beneficiary: Optional["UsersRead"] = None
    tontine: Optional["TontinesRead"] = None
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
