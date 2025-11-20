

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.feeschedules import FeeSchedulesRead
    from app.schemas.fxrates import FxRatesRead
    from app.schemas.provideraccounts import ProviderAccountsRead


class ProvidersBase(BaseModel):
    provider_id: str
    name: str
    type: str
    active: bool
    created_at: datetime
    updated_at: datetime
    country_code: Optional[str]

class ProvidersCreate(ProvidersBase):
    provider_id: str
    name: str
    type: str
    active: bool
    country_code: Optional[str]

class ProvidersUpdate(BaseModel):
    provider_id: Optional[str]
    name: Optional[str]
    type: Optional[str]
    active: Optional[bool]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    country_code: Optional[Optional[str]]

class ProvidersRead(ProvidersBase):
    provider_id: str
    name: str
    type: str
    active: bool
    created_at: datetime
    updated_at: datetime
    country_code: Optional[str]
    fee_schedules: list["FeeSchedulesRead"] = None
    fx_rates: list["FxRatesRead"] = None
    provider_accounts: list["ProviderAccountsRead"] = None
    class Config:
        from_attributes = True
