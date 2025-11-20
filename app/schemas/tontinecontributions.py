

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


class TontineContributionsBase(BaseModel):
    contribution_id: str
    tontine_id: str
    user_id: str
    amount: decimal.Decimal
    paid_at: datetime
    tx_id: Optional[str]

class TontineContributionsCreate(TontineContributionsBase):
    contribution_id: str
    tontine_id: str
    user_id: str
    amount: decimal.Decimal
    paid_at: datetime
    tx_id: Optional[str]

class TontineContributionsUpdate(BaseModel):
    contribution_id: Optional[str]
    tontine_id: Optional[str]
    user_id: Optional[str]
    amount: Optional[decimal.Decimal]
    paid_at: Optional[datetime]
    tx_id: Optional[Optional[str]]

class TontineContributionsRead(TontineContributionsBase):
    contribution_id: str
    tontine_id: str
    user_id: str
    amount: decimal.Decimal
    paid_at: datetime
    tx_id: Optional[str]
    tontine: Optional["TontinesRead"] = None
    tx: Optional["TransactionsRead"] = None
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
