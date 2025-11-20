

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.webhookevents import WebhookEventsRead

class WebhooksBase(BaseModel):
    webhook_id: str
    subscriber_url: str
    event_types: str
    secret: str
    status: str
    created_at: datetime

class WebhooksCreate(WebhooksBase):
    webhook_id: str
    subscriber_url: str
    event_types: str
    secret: str
    status: str

class WebhooksUpdate(BaseModel):
    webhook_id: Optional[str]
    subscriber_url: Optional[str]
    event_types: Optional[str]
    secret: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]

class WebhooksRead(WebhooksBase):
    webhook_id: str
    subscriber_url: str
    event_types: str
    secret: str
    status: str
    created_at: datetime
    webhook_events: list["WebhookEventsRead"] = None
    class Config:
        from_attributes = True
