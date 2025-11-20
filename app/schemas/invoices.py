# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

#



if TYPE_CHECKING:
    from app.schemas.billpayments import BillPaymentsRead
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.merchants import MerchantsRead
    from app.schemas.users import UsersRead
class InvoicesBase(BaseModel):
    invoice_id: str
    merchant_id: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    customer_user: Optional[str]
    due_date: Optional[datetime]
    metadata: Optional[dict]

class InvoicesCreate(InvoicesBase):
    invoice_id: str
    merchant_id: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    customer_user: Optional[str]
    due_date: Optional[datetime]
    metadata: Optional[dict]

class InvoicesUpdate(BaseModel):
    invoice_id: Optional[str]
    merchant_id: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    customer_user: Optional[Optional[str]]
    due_date: Optional[Optional[datetime]]
    metadata: Optional[Optional[dict]]

class InvoicesRead(InvoicesBase):
    invoice_id: str
    merchant_id: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    customer_user: Optional[str]
    due_date: Optional[datetime]
    metadata: Optional[dict]
    currencies: Optional["CurrenciesRead"] = None
    users: Optional["UsersRead"] = None
    merchant: Optional["MerchantsRead"] = None
    bill_payments: Optional[List["BillPaymentsRead"]] = None  # ✅ forward ref
    class Config:
        from_attributes = True
