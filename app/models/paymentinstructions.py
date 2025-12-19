# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PaymentInstructions(Base):
    __tablename__ = 'payment_instructions'
    __table_args__ = (
        CheckConstraint("status = ANY (ARRAY['pending'::paylink.tx_status, 'succeeded'::paylink.tx_status, 'failed'::paylink.tx_status, 'reversed'::paylink.tx_status, 'cancelled'::paylink.tx_status])", name='pi_status_consistency'),
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='payment_instructions_currency_code_fkey'),
        ForeignKeyConstraint(['provider_account_id'], ['paylink.provider_accounts.provider_account_id'], name='payment_instructions_provider_account_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], ondelete='CASCADE', name='payment_instructions_tx_id_fkey'),
        PrimaryKeyConstraint('pi_id', name='payment_instructions_pkey'),
        Index('idx_pi_status', 'status'),
        Index('idx_pi_tx', 'tx_id'),
        {'schema': 'paylink'}
    )

    pi_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    direction: Mapped[str] = mapped_column(Enum('credit', 'debit','CREDIT', 'DEBIT', name='tx_direction', schema='paylink'), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(Enum('initiated', 'pending', 'succeeded', 'failed', 'cancelled', 'reversed', 'chargeback', name='tx_status', schema='paylink'), nullable=False, server_default=text("'pending'::paylink.tx_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    provider_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    country_code: Mapped[Optional[str]] = mapped_column(CHAR(2))
    request_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='payment_instructions')
    provider_account: Mapped[Optional['ProviderAccounts']] = relationship('ProviderAccounts', back_populates='payment_instructions')
    tx: Mapped['Transactions'] = relationship('Transactions', back_populates='payment_instructions')

from app.models.currencies import Currencies
from app.models.provideraccounts import ProviderAccounts
from app.models.transactions import Transactions
