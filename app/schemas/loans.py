

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.loanrepayments import LoanRepaymentsRead
    from app.schemas.users import UsersRead


class LoansBase(BaseModel):
    loan_id: str
    borrower_user: str
    principal: decimal.Decimal
    currency_code: str
    apr_percent: decimal.Decimal
    term_months: int
    status: str
    created_at: datetime
    updated_at: datetime
    risk_level: Optional[str]

class LoansCreate(LoansBase):
    loan_id: str
    borrower_user: str
    principal: decimal.Decimal
    currency_code: str
    apr_percent: decimal.Decimal
    term_months: int
    status: str
    risk_level: Optional[str]

class LoansUpdate(BaseModel):
    loan_id: Optional[str]
    borrower_user: Optional[str]
    principal: Optional[decimal.Decimal]
    currency_code: Optional[str]
    apr_percent: Optional[decimal.Decimal]
    term_months: Optional[int]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    risk_level: Optional[Optional[str]]

class LoansRead(LoansBase):
    loan_id: str
    borrower_user: str
    principal: decimal.Decimal
    currency_code: str
    apr_percent: decimal.Decimal
    term_months: int
    status: str
    created_at: datetime
    updated_at: datetime
    risk_level: Optional[str]
    users: Optional["UsersRead"] = None
    currencies: Optional["CurrenciesRead"] = None
    loan_repayments: list["LoanRepaymentsRead"] = None
    class Config:
        from_attributes = True
