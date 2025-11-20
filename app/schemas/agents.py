from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.agentlocations import AgentLocationsRead
    from app.schemas.countries import CountriesRead
    from app.schemas.users import UsersRead


class AgentsBase(BaseModel):
    agent_id: str
    display_name: str
    country_code: str
    active: bool
    created_at: datetime
    user_id: Optional[str] = None


class AgentsCreate(AgentsBase):
    pass


class AgentsUpdate(BaseModel):
    display_name: Optional[str] = None
    active: Optional[bool] = None


class AgentsRead(AgentsBase):
    countries: Optional["CountriesRead"] = None
    user: Optional["UsersRead"] = None
    locations: Optional[List["AgentLocationsRead"]] = None

    class Config:
        from_attributes = True
