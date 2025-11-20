
# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.transactions import TransactionsRead
    from app.schemas.users import UsersRead



class DisputesBase(BaseModel):
    dispute_id: str
    tx_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    opened_by: Optional[str]
    reason: Optional[str]
    evidence_url: Optional[str]

class DisputesCreate(DisputesBase):
    dispute_id: str
    tx_id: str
    status: str
    opened_by: Optional[str]
    reason: Optional[str]
    evidence_url: Optional[str]

class DisputesUpdate(BaseModel):
    dispute_id: Optional[str]
    tx_id: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    opened_by: Optional[Optional[str]]
    reason: Optional[Optional[str]]
    evidence_url: Optional[Optional[str]]

class DisputesRead(DisputesBase):
    dispute_id: str
    tx_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    opened_by: Optional[str]
    reason: Optional[str]
    evidence_url: Optional[str]
    users: Optional["UsersRead"] = None
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
