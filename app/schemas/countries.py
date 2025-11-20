# app/schemas/countries.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

# ✅ Import uniquement pour l'éditeur (pas au runtime)
if TYPE_CHECKING:
    from app.schemas.agents import AgentsRead
    from app.schemas.users import UsersRead


class CountriesBase(BaseModel):
    country_code: str
    name: str
    currency_code: str
    created_at: datetime
    updated_at: datetime
    phone_prefix: Optional[str] = None


class CountriesCreate(CountriesBase):
    pass


class CountriesUpdate(BaseModel):
    country_code: Optional[str] = None
    name: Optional[str] = None
    currency_code: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    phone_prefix: Optional[str] = None


class CountriesRead(CountriesBase):
    users: Optional[List["UsersRead"]] = None
    agents: Optional[List["AgentsRead"]] = None

    class Config:
        from_attributes = True


