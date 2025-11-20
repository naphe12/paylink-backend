

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.transactions import TransactionsRead
    from app.schemas.users import UsersRead

class AmlEventsBase(BaseModel):
    aml_id: str
    rule_code: str
    risk_level: str
    created_at: datetime
    user_id: Optional[str]
    tx_id: Optional[str]
    details: Optional[dict]

class AmlEventsCreate(AmlEventsBase):
    aml_id: str
    rule_code: str
    risk_level: str
    user_id: Optional[str]
    tx_id: Optional[str]
    details: Optional[dict]

class AmlEventsUpdate(BaseModel):
    aml_id: Optional[str]
    rule_code: Optional[str]
    risk_level: Optional[str]
    created_at: Optional[datetime]
    user_id: Optional[Optional[str]]
    tx_id: Optional[Optional[str]]
    details: Optional[Optional[dict]]

class AmlEventsRead(AmlEventsBase):
    aml_id: str
    rule_code: str
    risk_level: str
    created_at: datetime
    user_id: Optional[str]
    tx_id: Optional[str]
    details: Optional[dict]
    tx: Optional["TransactionsRead"] = None
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
