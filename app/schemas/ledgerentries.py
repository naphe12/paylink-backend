
# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.ledgeraccounts import LedgerAccountsRead
    from app.schemas.ledgerjournal import LedgerJournalRead



class LedgerEntriesBase(BaseModel):
    entry_id: int
    journal_id: str
    account_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str

class LedgerEntriesCreate(LedgerEntriesBase):
    entry_id: int
    journal_id: str
    account_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str

class LedgerEntriesUpdate(BaseModel):
    entry_id: Optional[int]
    journal_id: Optional[str]
    account_id: Optional[str]
    direction: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]

class LedgerEntriesRead(LedgerEntriesBase):
    entry_id: int
    journal_id: str
    account_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str
    account: Optional["LedgerAccountsRead"] = None
    currencies: Optional["CurrenciesRead"] = None
    journal: Optional["LedgerJournalRead"] = None
    class Config:
        from_attributes = True
