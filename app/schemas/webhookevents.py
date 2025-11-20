

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.webhooks import WebhooksRead

class WebhookEventsBase(BaseModel):
    event_id: str
    webhook_id: str
    event_type: str
    payload: dict
    attempt_count: int
    status: str
    created_at: datetime
    last_attempt_at: Optional[datetime]

class WebhookEventsCreate(WebhookEventsBase):
    event_id: str
    webhook_id: str
    event_type: str
    payload: dict
    attempt_count: int
    status: str
    last_attempt_at: Optional[datetime]

class WebhookEventsUpdate(BaseModel):
    event_id: Optional[str]
    webhook_id: Optional[str]
    event_type: Optional[str]
    payload: Optional[dict]
    attempt_count: Optional[int]
    status: Optional[str]
    created_at: Optional[datetime]
    last_attempt_at: Optional[Optional[datetime]]

class WebhookEventsRead(WebhookEventsBase):
    event_id: str
    webhook_id: str
    event_type: str
    payload: dict
    attempt_count: int
    status: str
    created_at: datetime
    last_attempt_at: Optional[datetime]
    webhook: Optional["WebhooksRead"] = None
    class Config:
        from_attributes = True
