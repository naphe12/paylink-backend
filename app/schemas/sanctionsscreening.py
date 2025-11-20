

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.users import UsersRead

class SanctionsScreeningBase(BaseModel):
    screening_id: str
    user_id: str
    matched: bool
    created_at: datetime
    provider: Optional[str]
    payload: Optional[dict]

class SanctionsScreeningCreate(SanctionsScreeningBase):
    screening_id: str
    user_id: str
    matched: bool
    provider: Optional[str]
    payload: Optional[dict]

class SanctionsScreeningUpdate(BaseModel):
    screening_id: Optional[str]
    user_id: Optional[str]
    matched: Optional[bool]
    created_at: Optional[datetime]
    provider: Optional[Optional[str]]
    payload: Optional[Optional[dict]]

class SanctionsScreeningRead(SanctionsScreeningBase):
    screening_id: str
    user_id: str
    matched: bool
    created_at: datetime
    provider: Optional[str]
    payload: Optional[dict]
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
