# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IdempotencyKeysBase(BaseModel):
    key_id: str
    client_key: str
    created_at: datetime

class IdempotencyKeysCreate(IdempotencyKeysBase):
    key_id: str
    client_key: str

class IdempotencyKeysUpdate(BaseModel):
    key_id: Optional[str]
    client_key: Optional[str]
    created_at: Optional[datetime]

class IdempotencyKeysRead(IdempotencyKeysBase):
    key_id: str
    client_key: str
    created_at: datetime
    class Config:
        from_attributes = True