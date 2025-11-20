

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.ledgerentries import LedgerEntriesRead

class LedgerAccountsBase(BaseModel):
    account_id: str
    code: str
    name: str
    currency_code: str
    created_at: datetime
    metadata: Optional[dict]

class LedgerAccountsCreate(LedgerAccountsBase):
    account_id: str
    code: str
    name: str
    currency_code: str
    metadata: Optional[dict]

class LedgerAccountsUpdate(BaseModel):
    account_id: Optional[str]
    code: Optional[str]
    name: Optional[str]
    currency_code: Optional[str]
    created_at: Optional[datetime]
    metadata: Optional[Optional[dict]]

class LedgerAccountsRead(LedgerAccountsBase):
    account_id: str
    code: str
    name: str
    currency_code: str
    created_at: datetime
    metadata: Optional[dict]
    currencies: Optional["CurrenciesRead"] = None
    ledger_entries: list["LedgerEntriesRead"] = None
    class Config:
        from_attributes = True
