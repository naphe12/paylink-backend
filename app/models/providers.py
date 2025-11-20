# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Providers(Base):
    __tablename__ = 'providers'
    __table_args__ = (
        PrimaryKeyConstraint('provider_id', name='providers_pkey'),
        Index('idx_providers_type', 'type'),
        {'schema': 'paylink'}
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Enum('mobile_money', 'bank', 'aggregator', 'card_processor', 'fx_oracle', name='provider_type', schema='paylink'), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    country_code: Mapped[Optional[str]] = mapped_column(CHAR(2))

    fee_schedules: Mapped[list['FeeSchedules']] = relationship('FeeSchedules', back_populates='provider')
    fx_rates: Mapped[list['FxRates']] = relationship('FxRates', back_populates='provider')
    provider_accounts: Mapped[list['ProviderAccounts']] = relationship('ProviderAccounts', back_populates='provider')

from app.models.feeschedules import FeeSchedules
from app.models.fxrates import FxRates
from app.models.provideraccounts import ProviderAccounts

t_v_journal_balanced = Table(
    'v_journal_balanced', Base.metadata,
    Column('journal_id', Uuid),
    Column('total_debit', Numeric),
    Column('total_credit', Numeric),
    schema='paylink'
)


t_v_system_health_dashboard = Table(
    'v_system_health_dashboard', Base.metadata,
    Column('currency_code', CHAR(3)),
    Column('nb_wallets', BigInteger),
    Column('balance_wallets', Numeric),
    Column('balance_ledger', Numeric),
    Column('difference_wallet_ledger', Numeric),
    Column('wallets_desync', BigInteger),
    Column('wallets_total', BigInteger),
    Column('desync_rate_percent', Numeric),
    Column('total_income_fees', Numeric),
    schema='paylink'
)


t_v_wallet_balance_ledger = Table(
    'v_wallet_balance_ledger', Base.metadata,
    Column('account_id', Uuid),
    Column('ledger_code', Text),
    Column('wallet_id', Uuid),
    Column('user_id', Uuid),
    Column('owner_name', Text),
    Column('currency_code', CHAR(3)),
    Column('ledger_balance', Numeric(20, 6)),
    Column('nb_entries', BigInteger),
    schema='paylink'
)


t_v_wallet_initialization_audit = Table(
    'v_wallet_initialization_audit', Base.metadata,
    Column('wallet_id', Uuid),
    Column('user_id', Uuid),
    Column('owner_name', Text),
    Column('currency_code', CHAR(3)),
    Column('balance_wallet', Numeric(20, 6)),
    Column('balance_ledger', Numeric(20, 6)),
    Column('difference', Numeric),
    Column('audit_status', Text),
    schema='paylink'
)


t_v_wallet_reconciliation = Table(
    'v_wallet_reconciliation', Base.metadata,
    Column('wallet_id', Uuid),
    Column('user_id', Uuid),
    Column('owner_name', Text),
    Column('currency_code', CHAR(3)),
    Column('balance_stored', Numeric(20, 6)),
    Column('balance_ledger', Numeric(20, 6)),
    Column('difference', Numeric),
    Column('status', Text),
    schema='paylink'
)


t_v_wallet_reconciliation_summary = Table(
    'v_wallet_reconciliation_summary', Base.metadata,
    Column('currency_code', CHAR(3)),
    Column('total_wallets', BigInteger),
    Column('nb_desync', BigInteger),
    Column('total_difference', Numeric),
    schema='paylink'
)
