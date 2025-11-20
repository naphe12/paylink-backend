

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.amlevents import AmlEventsRead
    from app.schemas.billpayments import BillPaymentsRead
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.disputes import DisputesRead
    from app.schemas.fxconversions import FxConversionsRead
    from app.schemas.loanrepayments import LoanRepaymentsRead
    from app.schemas.paymentinstructions import PaymentInstructionsRead
    from app.schemas.reconlines import ReconLinesRead
    from app.schemas.tontinecontributions import TontineContributionsRead
    from app.schemas.tontinepayouts import TontinePayoutsRead
    from app.schemas.users import UsersRead
    from app.schemas.wallets import WalletsRead


class TransactionsBase(BaseModel):
    tx_id: str
    amount: decimal.Decimal
    currency_code: str
    channel: str
    status: str
    created_at: datetime
    updated_at: datetime
    initiated_by: Optional[str]
    sender_wallet: Optional[str]
    receiver_wallet: Optional[str]
    external_ref: Optional[str]
    description: Optional[str]

class TransactionsCreate(TransactionsBase):
    tx_id: str
    amount: decimal.Decimal
    currency_code: str
    channel: str
    status: str
    initiated_by: Optional[str]
    sender_wallet: Optional[str]
    receiver_wallet: Optional[str]
    external_ref: Optional[str]
    description: Optional[str]

class TransactionsUpdate(BaseModel):
    tx_id: Optional[str]
    amount: Optional[decimal.Decimal]
    currency_code: Optional[str]
    channel: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    initiated_by: Optional[Optional[str]]
    sender_wallet: Optional[Optional[str]]
    receiver_wallet: Optional[Optional[str]]
    external_ref: Optional[Optional[str]]
    description: Optional[Optional[str]]

class TransactionsRead(TransactionsBase):
    tx_id: str
    amount: decimal.Decimal
    currency_code: str
    channel: str
    status: str
    created_at: datetime
    updated_at: datetime
    initiated_by: Optional[str]
    sender_wallet: Optional[str]
    receiver_wallet: Optional[str]
    external_ref: Optional[str]
    description: Optional[str]
    currencies: Optional["CurrenciesRead"] = None
    users: Optional["UsersRead"] = None
    wallets: Optional["WalletsRead"] = None
    wallets_: Optional["WalletsRead"] = None
    aml_events: list["AmlEventsRead"] = None
    disputes: list["DisputesRead"] = None
    fx_conversions: list["FxConversionsRead"] = None
    loan_repayments: list["LoanRepaymentsRead"] = None
    payment_instructions: list["PaymentInstructionsRead"] = None
    recon_lines: list["ReconLinesRead"] = None
    tontine_contributions: list["TontineContributionsRead"] = None
    tontine_payouts: list["TontinePayoutsRead"] = None
    bill_payments: list["BillPaymentsRead"] = None
    class Config:
        from_attributes = True

class TransactionListItem(BaseModel):
    tx_id: str
    amount: float
    status: str
    created_at: datetime
    direction: str  # "sent" or "received"
    description: Optional[str]

    class Config:
        from_attributes = True

# app/schemas/transactions.py
class TransactionSend(BaseModel):
    to_identifier: str  # email ou téléphone
    amount: float
    description: Optional[str] = None

