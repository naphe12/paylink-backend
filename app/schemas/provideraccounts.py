

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.paymentinstructions import PaymentInstructionsRead
    from app.schemas.providers import ProvidersRead
    from app.schemas.reconfiles import ReconFilesRead
    from app.schemas.settlements import SettlementsRead




class ProviderAccountsBase(BaseModel):
    provider_account_id: str
    provider_id: str
    display_name: str
    credentials: dict
    active: bool
    created_at: datetime
    updated_at: datetime
    currency_code: Optional[str]
    webhook_secret: Optional[str]

class ProviderAccountsCreate(ProviderAccountsBase):
    provider_account_id: str
    provider_id: str
    display_name: str
    credentials: dict
    active: bool
    currency_code: Optional[str]
    webhook_secret: Optional[str]

class ProviderAccountsUpdate(BaseModel):
    provider_account_id: Optional[str]
    provider_id: Optional[str]
    display_name: Optional[str]
    credentials: Optional[dict]
    active: Optional[bool]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    currency_code: Optional[Optional[str]]
    webhook_secret: Optional[Optional[str]]

class ProviderAccountsRead(ProviderAccountsBase):
    provider_account_id: str
    provider_id: str
    display_name: str
    credentials: dict
    active: bool
    created_at: datetime
    updated_at: datetime
    currency_code: Optional[str]
    webhook_secret: Optional[str]
    currencies: Optional["CurrenciesRead"] = None
    provider: Optional["ProvidersRead"] = None
    recon_files: list["ReconFilesRead"] = None
    settlements: list["SettlementsRead"] = None
    payment_instructions: list["PaymentInstructionsRead"] = None
    class Config:
        from_attributes = True
