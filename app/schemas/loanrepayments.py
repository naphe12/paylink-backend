

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.loans import LoansRead
    from app.schemas.transactions import TransactionsRead

class LoanRepaymentsBase(BaseModel):
    repayment_id: str
    loan_id: str
    due_date: datetime
    due_amount: decimal.Decimal
    tx_id: Optional[str]
    paid_amount: Optional[decimal.Decimal]
    paid_at: Optional[datetime]

class LoanRepaymentsCreate(LoanRepaymentsBase):
    repayment_id: str
    loan_id: str
    due_date: datetime
    due_amount: decimal.Decimal
    tx_id: Optional[str]
    paid_amount: Optional[decimal.Decimal]
    paid_at: Optional[datetime]

class LoanRepaymentsUpdate(BaseModel):
    repayment_id: Optional[str]
    loan_id: Optional[str]
    due_date: Optional[datetime]
    due_amount: Optional[decimal.Decimal]
    tx_id: Optional[Optional[str]]
    paid_amount: Optional[Optional[decimal.Decimal]]
    paid_at: Optional[Optional[datetime]]

class LoanRepaymentsRead(LoanRepaymentsBase):
    repayment_id: str
    loan_id: str
    due_date: datetime
    due_amount: decimal.Decimal
    tx_id: Optional[str]
    paid_amount: Optional[decimal.Decimal]
    paid_at: Optional[datetime]
    loan: Optional["LoansRead"] = None
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
