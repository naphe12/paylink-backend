# Auto-generated from database schema
import decimal
import uuid

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LedgerEntries(Base):
    __tablename__ = 'ledger_entries'
    __table_args__ = (
        CheckConstraint('amount > 0::numeric', name='ledger_entries_amount_check'),
        ForeignKeyConstraint(['account_id'], ['paylink.ledger_accounts.account_id'], name='ledger_entries_account_id_fkey'),
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='ledger_entries_currency_code_fkey'),
        ForeignKeyConstraint(['journal_id'], ['paylink.ledger_journal.journal_id'], ondelete='CASCADE', name='ledger_entries_journal_id_fkey'),
        PrimaryKeyConstraint('entry_id', name='ledger_entries_pkey'),
        Index('idx_entries_account', 'account_id'),
        Index('idx_entries_journal', 'journal_id'),
        {'schema': 'paylink'}
    )

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    direction: Mapped[str] = mapped_column(Enum('credit', 'debit', name='tx_direction', schema='paylink'), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)

    account: Mapped['LedgerAccounts'] = relationship('LedgerAccounts', back_populates='ledger_entries')
    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='ledger_entries')
    journal: Mapped['LedgerJournal'] = relationship('LedgerJournal', back_populates='ledger_entries')

from app.models.currencies import Currencies
from app.models.ledgeraccounts import LedgerAccounts
from app.models.ledgerjournal import LedgerJournal
