# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgentLocationsBase(BaseModel):
    location_id: str
    agent_id: str
    created_at: datetime
    label: Optional[str]
    lat: Optional[decimal.Decimal]
    lng: Optional[decimal.Decimal]
    address: Optional[str]


class AgentLocationsCreate(AgentLocationsBase):
    label: Optional[str]
    lat: Optional[decimal.Decimal]
    lng: Optional[decimal.Decimal]
    address: Optional[str]


class AgentLocationsUpdate(BaseModel):
    location_id: Optional[str]
    agent_id: Optional[str]
    created_at: Optional[datetime]
    label: Optional[str]
    lat: Optional[decimal.Decimal]
    lng: Optional[decimal.Decimal]
    address: Optional[str]


class AgentLocationsRead(AgentLocationsBase):
    agent: Optional["AgentsRead"] = None  # type: ignore[name-defined]

    class Config:
        from_attributes = True

