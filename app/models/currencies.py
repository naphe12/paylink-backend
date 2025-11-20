# Auto-generated from database schema
import datetime

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import relationship

from app.core.database import Base


class Currencies(Base):
    __tablename__ = 'currencies'
    __table_args__ = (
        CheckConstraint('decimals >= 0 AND decimals <= 6', name='currencies_decimals_check'),
        PrimaryKeyConstraint('currency_code', name='currencies_pkey'),
        {'schema': 'paylink'}
    )

    currency_code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('2'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    fee_schedules: Mapped[list['FeeSchedules']] = relationship('FeeSchedules', back_populates='currencies')
    fx_rates: Mapped[list['FxRates']] = relationship('FxRates', foreign_keys='[FxRates.base_currency]', back_populates='currencies')
    fx_rates_: Mapped[list['FxRates']] = relationship('FxRates', foreign_keys='[FxRates.quote_currency]', back_populates='currencies_')
    ledger_accounts: Mapped[list['LedgerAccounts']] = relationship('LedgerAccounts', back_populates='currencies')
    limits: Mapped[list['Limits']] = relationship('Limits', back_populates='currencies')
    provider_accounts: Mapped[list['ProviderAccounts']] = relationship('ProviderAccounts', back_populates='currencies')
    ledger_entries: Mapped[list['LedgerEntries']] = relationship('LedgerEntries', back_populates='currencies')
    loans: Mapped[list['Loans']] = relationship('Loans', back_populates='currencies')
    settlements: Mapped[list['Settlements']] = relationship('Settlements', back_populates='currencies')
    tontines: Mapped[list['Tontines']] = relationship('Tontines', back_populates='currencies')
    wallets = relationship(
    "Wallets",
    back_populates="currencies",
    primaryjoin="foreign(Wallets.currency_code) == Currencies.currency_code"
)
    transactions: Mapped[list['Transactions']] = relationship('Transactions', back_populates='currencies')

    fx_conversions: Mapped[list['FxConversions']] = relationship('FxConversions', foreign_keys='[FxConversions.from_currency]', back_populates='currencies')
    fx_conversions_: Mapped[list['FxConversions']] = relationship('FxConversions', foreign_keys='[FxConversions.to_currency]', back_populates='currencies_')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='currencies')
    payment_instructions: Mapped[list['PaymentInstructions']] = relationship('PaymentInstructions', back_populates='currencies')
    recon_lines: Mapped[list['ReconLines']] = relationship('ReconLines', back_populates='currencies')


from app.models.feeschedules import FeeSchedules
from app.models.fxconversions import FxConversions
from app.models.fxrates import FxRates
from app.models.invoices import Invoices
from app.models.ledgeraccounts import LedgerAccounts
from app.models.ledgerentries import LedgerEntries
from app.models.limits import Limits
from app.models.loans import Loans
from app.models.paymentinstructions import PaymentInstructions
from app.models.provideraccounts import ProviderAccounts
from app.models.reconlines import ReconLines
from app.models.settlements import Settlements
from app.models.tontines import Tontines
from app.models.transactions import Transactions
from app.models.wallets import Wallets
