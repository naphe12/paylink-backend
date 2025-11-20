

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.ledgerentries import LedgerEntriesRead

class LedgerJournalBase(BaseModel):
    journal_id: str
    occurred_at: datetime
    tx_id: Optional[str]
    description: Optional[str]
    metadata: Optional[dict]

class LedgerJournalCreate(LedgerJournalBase):
    journal_id: str
    occurred_at: datetime
    tx_id: Optional[str]
    description: Optional[str]
    metadata: Optional[dict]

class LedgerJournalUpdate(BaseModel):
    journal_id: Optional[str]
    occurred_at: Optional[datetime]
    tx_id: Optional[Optional[str]]
    description: Optional[Optional[str]]
    metadata: Optional[Optional[dict]]

class LedgerJournalRead(LedgerJournalBase):
    journal_id: str
    occurred_at: datetime
    tx_id: Optional[str]
    description: Optional[str]
    metadata: Optional[dict]
    ledger_entries: list["LedgerEntriesRead"] = None
    class Config:
        from_attributes = True
