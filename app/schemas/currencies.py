# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

#
#
#



#










if TYPE_CHECKING:
    from app.schemas.feeschedules import FeeSchedulesRead
    from app.schemas.fxconversions import FxConversionsRead
    from app.schemas.fxrates import FxRatesRead
    from app.schemas.invoices import InvoicesRead
    from app.schemas.ledgeraccounts import LedgerAccountsRead
    from app.schemas.ledgerentries import LedgerEntriesRead
    from app.schemas.limits import LimitsRead
    from app.schemas.loans import LoansRead
    from app.schemas.paymentinstructions import PaymentInstructionsRead
    from app.schemas.provideraccounts import ProviderAccountsRead
    from app.schemas.reconlines import ReconLinesRead
    from app.schemas.settlements import SettlementsRead
    from app.schemas.tontines import TontinesRead
    from app.schemas.transactions import TransactionsRead
    from app.schemas.wallets import WalletsRead
if TYPE_CHECKING:
    from app.schemas.feeschedules import FeeSchedulesRead
    from app.schemas.fxconversions import FxConversionsRead
    from app.schemas.fxrates import FxRatesRead
    from app.schemas.invoices import InvoicesRead
    from app.schemas.ledgeraccounts import LedgerAccountsRead
    from app.schemas.ledgerentries import LedgerEntriesRead
    from app.schemas.limits import LimitsRead
    from app.schemas.loans import LoansRead
    from app.schemas.paymentinstructions import PaymentInstructionsRead
    from app.schemas.provideraccounts import ProviderAccountsRead
    from app.schemas.reconlines import ReconLinesRead
    from app.schemas.settlements import SettlementsRead
    from app.schemas.tontines import TontinesRead
    from app.schemas.transactions import TransactionsRead
    from app.schemas.wallets import WalletsRead


class CurrenciesBase(BaseModel):
    currency_code: str
    name: str
    decimals: int
    created_at: datetime
    updated_at: datetime

class CurrenciesCreate(CurrenciesBase):
    currency_code: str
    name: str
    decimals: int

class CurrenciesUpdate(BaseModel):
    currency_code: Optional[str]
    name: Optional[str]
    decimals: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

class CurrenciesRead(CurrenciesBase):
    currency_code: str
    name: str
    decimals: int
    created_at: datetime
    updated_at: datetime
    fee_schedules: Optional[List["FeeSchedulesRead"]] = None
    fx_rates_from: Optional[List["FxRatesRead"]] = None
    fx_rates_to: Optional[List["FxRatesRead"]] = None
    ledger_accounts: list["LedgerAccountsRead"] = None
    #limits: list[LimitsRead] = None
    provider_accounts: list["ProviderAccountsRead"] = None
    ledger_entries: list["LedgerEntriesRead"] = None
    loans: list["LoansRead"] = None
    settlements: list["SettlementsRead"] = None
    tontines: list["TontinesRead"] = None
    wallets: list["WalletsRead"] = None
    transactions: list["TransactionsRead"] = None
    fx_conversions_from: Optional[List["FxConversionsRead"]] = None
    fx_conversions_to: Optional[List["FxConversionsRead"]] = None
    limits: Optional[List["LimitsRead"]] = None
    invoices: list["InvoicesRead"] = None
    payment_instructions: list["PaymentInstructionsRead"] = None
    recon_lines: list["ReconLinesRead"] = None
    class Config:
        from_attributes = True
