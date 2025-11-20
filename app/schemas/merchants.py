

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.invoices import InvoicesRead
    from app.schemas.users import UsersRead
    from app.schemas.wallets import WalletsRead


class MerchantsBase(BaseModel):
    merchant_id: str
    legal_name: str
    country_code: str
    active: bool
    created_at: datetime
    user_id: Optional[str]
    tax_id: Optional[str]
    settlement_wallet: Optional[str]

class MerchantsCreate(MerchantsBase):
    merchant_id: str
    legal_name: str
    country_code: str
    active: bool
    user_id: Optional[str]
    tax_id: Optional[str]
    settlement_wallet: Optional[str]

class MerchantsUpdate(BaseModel):
    merchant_id: Optional[str]
    legal_name: Optional[str]
    country_code: Optional[str]
    active: Optional[bool]
    created_at: Optional[datetime]
    user_id: Optional[Optional[str]]
    tax_id: Optional[Optional[str]]
    settlement_wallet: Optional[Optional[str]]

class MerchantsRead(MerchantsBase):
    merchant_id: str
    legal_name: str
    country_code: str
    active: bool
    created_at: datetime
    user_id: Optional[str]
    tax_id: Optional[str]
    settlement_wallet: Optional[str]
    wallets: Optional["WalletsRead"] = None
    user: Optional["UsersRead"] = None
    invoices: list["InvoicesRead"] = None
    class Config:
        from_attributes = True
