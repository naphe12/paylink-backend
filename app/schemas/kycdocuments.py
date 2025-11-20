

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.users import UsersRead
class KycDocumentsBase(BaseModel):
    kyc_id: str
    user_id: str
    doc_type: str
    file_url: str
    verified: bool
    created_at: datetime
    updated_at: datetime
    doc_number: Optional[str]
    issued_country: Optional[str]
    expires_on: Optional[datetime]
    reviewer_user: Optional[str]
    notes: Optional[str]

class KycDocumentsCreate(KycDocumentsBase):
    kyc_id: str
    user_id: str
    doc_type: str
    file_url: str
    verified: bool
    doc_number: Optional[str]
    issued_country: Optional[str]
    expires_on: Optional[datetime]
    reviewer_user: Optional[str]
    notes: Optional[str]

class KycDocumentsUpdate(BaseModel):
    kyc_id: Optional[str]
    user_id: Optional[str]
    doc_type: Optional[str]
    file_url: Optional[str]
    verified: Optional[bool]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    doc_number: Optional[Optional[str]]
    issued_country: Optional[Optional[str]]
    expires_on: Optional[Optional[datetime]]
    reviewer_user: Optional[Optional[str]]
    notes: Optional[Optional[str]]

class KycDocumentsRead(KycDocumentsBase):
    kyc_id: str
    user_id: str
    doc_type: str
    file_url: str
    verified: bool
    created_at: datetime
    updated_at: datetime
    doc_number: Optional[str]
    issued_country: Optional[str]
    expires_on: Optional[datetime]
    reviewer_user: Optional[str]
    notes: Optional[str]
    users: Optional["UsersRead"] = None
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
