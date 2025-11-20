

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.reconfiles import ReconFilesRead
    from app.schemas.transactions import TransactionsRead

class ReconLinesBase(BaseModel):
    recon_line_id: int
    recon_id: str
    status: str
    external_ref: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    matched_tx: Optional[str]
    details: Optional[dict]

class ReconLinesCreate(ReconLinesBase):
    recon_line_id: int
    recon_id: str
    status: str
    external_ref: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    matched_tx: Optional[str]
    details: Optional[dict]

class ReconLinesUpdate(BaseModel):
    recon_line_id: Optional[int]
    recon_id: Optional[str]
    status: Optional[str]
    external_ref: Optional[Optional[str]]
    amount: Optional[Optional[decimal.Decimal]]
    currency_code: Optional[Optional[str]]
    matched_tx: Optional[Optional[str]]
    details: Optional[Optional[dict]]

class ReconLinesRead(ReconLinesBase):
    recon_line_id: int
    recon_id: str
    status: str
    external_ref: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    matched_tx: Optional[str]
    details: Optional[dict]
    currencies: Optional["CurrenciesRead"] = None
    transactions: Optional["TransactionsRead"] = None
    recon: Optional["ReconFilesRead"] = None
    class Config:
        from_attributes = True
