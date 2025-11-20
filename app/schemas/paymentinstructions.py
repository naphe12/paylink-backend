

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.provideraccounts import ProviderAccountsRead
    from app.schemas.transactions import TransactionsRead


class PaymentInstructionsBase(BaseModel):
    pi_id: str
    tx_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    provider_account_id: Optional[str]
    country_code: Optional[str]
    request_payload: Optional[dict]
    response_payload: Optional[dict]

class PaymentInstructionsCreate(PaymentInstructionsBase):
    pi_id: str
    tx_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    provider_account_id: Optional[str]
    country_code: Optional[str]
    request_payload: Optional[dict]
    response_payload: Optional[dict]

class PaymentInstructionsUpdate(BaseModel):
    pi_id: Optional[str]
    tx_id: Optional[str]
    direction: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    provider_account_id: Optional[Optional[str]]
    country_code: Optional[Optional[str]]
    request_payload: Optional[Optional[dict]]
    response_payload: Optional[Optional[dict]]

class PaymentInstructionsRead(PaymentInstructionsBase):
    pi_id: str
    tx_id: str
    direction: str
    amount: decimal.Decimal
    currency_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    provider_account_id: Optional[str]
    country_code: Optional[str]
    request_payload: Optional[dict]
    response_payload: Optional[dict]
    currencies: Optional["CurrenciesRead"] = None
    provider_account: Optional["ProviderAccountsRead"] = None
    tx: Optional["TransactionsRead"] = None
    class Config:
        from_attributes = True
