# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

#


if TYPE_CHECKING:
    from app.schemas.invoices import InvoicesRead
    from app.schemas.transactions import TransactionsRead
    

class BillPaymentsBase(BaseModel):
    bill_payment_id: str
    invoice_id: str
    paid_amount: decimal.Decimal
    created_at: datetime
    tx_id: Optional[str]

class BillPaymentsCreate(BillPaymentsBase):
    bill_payment_id: str
    invoice_id: str
    paid_amount: decimal.Decimal
    tx_id: Optional[str]

class BillPaymentsUpdate(BaseModel):
    bill_payment_id: Optional[str]
    invoice_id: Optional[str]
    paid_amount: Optional[decimal.Decimal]
    created_at: Optional[datetime]
    tx_id: Optional[Optional[str]]

class BillPaymentsRead(BillPaymentsBase):
    bill_payment_id: str
    invoice_id: str
    paid_amount: decimal.Decimal
    created_at: datetime
    tx_id: Optional[str]
    invoice: Optional["InvoicesRead"] = None  # ✅ forward ref
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
