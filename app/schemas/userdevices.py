

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.users import UsersRead
class UserDevicesBase(BaseModel):
    device_id: str
    user_id: str
    created_at: datetime
    device_fingerprint: Optional[str]
    push_token: Optional[str]

class UserDevicesCreate(UserDevicesBase):
    device_id: str
    user_id: str
    device_fingerprint: Optional[str]
    push_token: Optional[str]

class UserDevicesUpdate(BaseModel):
    device_id: Optional[str]
    user_id: Optional[str]
    created_at: Optional[datetime]
    device_fingerprint: Optional[Optional[str]]
    push_token: Optional[Optional[str]]

class UserDevicesRead(UserDevicesBase):
    device_id: str
    user_id: str
    created_at: datetime
    device_fingerprint: Optional[str]
    push_token: Optional[str]
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
