

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.users import UsersRead
class NotificationsBase(BaseModel):
    notification_id: str
    user_id: str
    channel: str
    created_at: datetime
    subject: Optional[str]
    message: Optional[str]
    metadata: Optional[dict]

class NotificationsCreate(NotificationsBase):
    notification_id: str
    user_id: str
    channel: str
    subject: Optional[str]
    message: Optional[str]
    metadata: Optional[dict]

class NotificationsUpdate(BaseModel):
    notification_id: Optional[str]
    user_id: Optional[str]
    channel: Optional[str]
    created_at: Optional[datetime]
    subject: Optional[Optional[str]]
    message: Optional[Optional[str]]
    metadata: Optional[Optional[dict]]

class NotificationsRead(NotificationsBase):
    notification_id: str
    user_id: str
    channel: str
    created_at: datetime
    subject: Optional[str]
    message: Optional[str]
    metadata: Optional[dict]
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
