import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import (ARRAY, CHAR, BigInteger, Boolean, CheckConstraint,
                        Column, Date, DateTime, Enum, ForeignKeyConstraint,
                        Index, Integer, Numeric, PrimaryKeyConstraint,
                        SmallInteger, Table, Text, UniqueConstraint, Uuid,
                        text)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Countries(Base):
    __tablename__ = 'countries'
    __table_args__ = (
        PrimaryKeyConstraint('country_code', name='countries_pkey'),
        {'schema': 'paylink'}
    )

    country_code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    phone_prefix: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[list['Users']] = relationship('Users', back_populates='countries')
    agents: Mapped[list['Agents']] = relationship('Agents', back_populates='countries')


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
    wallets: Mapped[list['Wallets']] = relationship('Wallets', back_populates='currencies')
    transactions: Mapped[list['Transactions']] = relationship('Transactions', back_populates='currencies')
    fx_conversions: Mapped[list['FxConversions']] = relationship('FxConversions', foreign_keys='[FxConversions.from_currency]', back_populates='currencies')
    fx_conversions_: Mapped[list['FxConversions']] = relationship('FxConversions', foreign_keys='[FxConversions.to_currency]', back_populates='currencies_')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='currencies')
    payment_instructions: Mapped[list['PaymentInstructions']] = relationship('PaymentInstructions', back_populates='currencies')
    recon_lines: Mapped[list['ReconLines']] = relationship('ReconLines', back_populates='currencies')


class IdempotencyKeys(Base):
    __tablename__ = 'idempotency_keys'
    __table_args__ = (
        PrimaryKeyConstraint('key_id', name='idempotency_keys_pkey'),
        UniqueConstraint('client_key', name='idempotency_keys_client_key_key'),
        {'schema': 'paylink'}
    )

    key_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    client_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class LedgerJournal(Base):
    __tablename__ = 'ledger_journal'
    __table_args__ = (
        PrimaryKeyConstraint('journal_id', name='ledger_journal_pkey'),
        {'schema': 'paylink'}
    )

    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    ledger_entries: Mapped[list['LedgerEntries']] = relationship('LedgerEntries', back_populates='journal')


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


class Webhooks(Base):
    __tablename__ = 'webhooks'
    __table_args__ = (
        PrimaryKeyConstraint('webhook_id', name='webhooks_pkey'),
        {'schema': 'paylink'}
    )

    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    subscriber_url: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Enum('queued', 'delivered', 'failed', 'disabled', name='webhook_status', schema='paylink'), nullable=False, server_default=text("'queued'::paylink.webhook_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    webhook_events: Mapped[list['WebhookEvents']] = relationship('WebhookEvents', back_populates='webhook')


class FeeSchedules(Base):
    __tablename__ = 'fee_schedules'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='fee_schedules_currency_code_fkey'),
        ForeignKeyConstraint(['provider_id'], ['paylink.providers.provider_id'], name='fee_schedules_provider_id_fkey'),
        PrimaryKeyConstraint('fee_id', name='fee_schedules_pkey'),
        Index('idx_fee_filters', 'channel', 'provider_id', 'country_code', 'currency_code'),
        {'schema': 'paylink'}
    )

    fee_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    channel: Mapped[Optional[str]] = mapped_column(Enum('mobile_money', 'bank', 'card', 'cash', 'internal', 'bank_transfer', name='tx_channel', schema='paylink'))
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    country_code: Mapped[Optional[str]] = mapped_column(CHAR(2))
    currency_code: Mapped[Optional[str]] = mapped_column(CHAR(3))
    min_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6), server_default=text('0'))
    max_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6))
    fixed_fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6), server_default=text('0'))
    percent_fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(7, 4), server_default=text('0'))

    currencies: Mapped[Optional['Currencies']] = relationship('Currencies', back_populates='fee_schedules')
    provider: Mapped[Optional['Providers']] = relationship('Providers', back_populates='fee_schedules')


class FxRates(Base):
    __tablename__ = 'fx_rates'
    __table_args__ = (
        CheckConstraint('rate > 0::numeric', name='fx_rates_rate_check'),
        ForeignKeyConstraint(['base_currency'], ['paylink.currencies.currency_code'], name='fx_rates_base_currency_fkey'),
        ForeignKeyConstraint(['provider_id'], ['paylink.providers.provider_id'], name='fx_rates_provider_id_fkey'),
        ForeignKeyConstraint(['quote_currency'], ['paylink.currencies.currency_code'], name='fx_rates_quote_currency_fkey'),
        PrimaryKeyConstraint('fx_id', name='fx_rates_pkey'),
        Index('idx_fx_pair_time', 'base_currency', 'quote_currency', 'obtained_at'),
        {'schema': 'paylink'}
    )

    fx_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    obtained_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    currencies: Mapped['Currencies'] = relationship('Currencies', foreign_keys=[base_currency], back_populates='fx_rates')
    provider: Mapped[Optional['Providers']] = relationship('Providers', back_populates='fx_rates')
    currencies_: Mapped['Currencies'] = relationship('Currencies', foreign_keys=[quote_currency], back_populates='fx_rates_')


class LedgerAccounts(Base):
    __tablename__ = 'ledger_accounts'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='ledger_accounts_currency_code_fkey'),
        PrimaryKeyConstraint('account_id', name='ledger_accounts_pkey'),
        UniqueConstraint('code', name='ledger_accounts_code_key'),
        {'schema': 'paylink'}
    )

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='ledger_accounts')
    ledger_entries: Mapped[list['LedgerEntries']] = relationship('LedgerEntries', back_populates='account')


class Limits(Base):
    __tablename__ = 'limits'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='limits_currency_code_fkey'),
        PrimaryKeyConstraint('limit_id', name='limits_pkey'),
        {'schema': 'paylink'}
    )

    limit_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    kyc_level: Mapped[Optional[str]] = mapped_column(Enum('unverified', 'pending', 'verified', 'rejected', name='kyc_status', schema='paylink'))
    currency_code: Mapped[Optional[str]] = mapped_column(CHAR(3))
    max_tx_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6))
    max_tx_count: Mapped[Optional[int]] = mapped_column(Integer)
    max_total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6))

    currencies: Mapped[Optional['Currencies']] = relationship('Currencies', back_populates='limits')
    limit_usage: Mapped[list['LimitUsage']] = relationship('LimitUsage', back_populates='limit')


class ProviderAccounts(Base):
    __tablename__ = 'provider_accounts'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='provider_accounts_currency_code_fkey'),
        ForeignKeyConstraint(['provider_id'], ['paylink.providers.provider_id'], ondelete='CASCADE', name='provider_accounts_provider_id_fkey'),
        PrimaryKeyConstraint('provider_account_id', name='provider_accounts_pkey'),
        Index('idx_provider_accounts_provider', 'provider_id'),
        {'schema': 'paylink'}
    )

    provider_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    credentials: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    currency_code: Mapped[Optional[str]] = mapped_column(CHAR(3))
    webhook_secret: Mapped[Optional[str]] = mapped_column(Text)

    currencies: Mapped[Optional['Currencies']] = relationship('Currencies', back_populates='provider_accounts')
    provider: Mapped['Providers'] = relationship('Providers', back_populates='provider_accounts')
    recon_files: Mapped[list['ReconFiles']] = relationship('ReconFiles', back_populates='provider_account')
    settlements: Mapped[list['Settlements']] = relationship('Settlements', back_populates='provider_account')
    payment_instructions: Mapped[list['PaymentInstructions']] = relationship('PaymentInstructions', back_populates='provider_account')


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        ForeignKeyConstraint(['country_code'], ['paylink.countries.country_code'], name='users_country_code_fkey'),
        ForeignKeyConstraint(['referred_by'], ['paylink.users.user_id'], name='users_referred_by_fkey'),
        PrimaryKeyConstraint('user_id', name='users_pkey'),
        UniqueConstraint('email', name='users_email_key'),
        UniqueConstraint('phone_e164', name='users_phone_e164_key'),
        Index('idx_users_country', 'country_code'),
        Index('idx_users_phone', 'phone_e164'),
        {'schema': 'paylink'}
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    status: Mapped[str] = mapped_column(Enum('pending', 'active', 'suspended', 'closed', name='user_status', schema='paylink'), nullable=False, server_default=text("'pending'::paylink.user_status"))
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    kyc_status: Mapped[str] = mapped_column(Enum('unverified', 'pending', 'verified', 'rejected', name='kyc_status', schema='paylink'), nullable=False, server_default=text("'unverified'::paylink.kyc_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    email: Mapped[Optional[str]] = mapped_column(CITEXT)
    phone_e164: Mapped[Optional[str]] = mapped_column(CITEXT)
    country_code: Mapped[Optional[str]] = mapped_column(CHAR(2))
    referred_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    countries: Mapped[Optional['Countries']] = relationship('Countries', back_populates='users')
    users: Mapped[Optional['Users']] = relationship('Users', remote_side=[user_id], back_populates='users_reverse')
    users_reverse: Mapped[list['Users']] = relationship('Users', remote_side=[referred_by], back_populates='users')
    agents: Mapped[Optional['Agents']] = relationship('Agents', uselist=False, back_populates='user')
    kyc_documents: Mapped[list['KycDocuments']] = relationship('KycDocuments', foreign_keys='[KycDocuments.reviewer_user]', back_populates='users')
    kyc_documents_: Mapped[list['KycDocuments']] = relationship('KycDocuments', foreign_keys='[KycDocuments.user_id]', back_populates='user')
    limit_usage: Mapped[list['LimitUsage']] = relationship('LimitUsage', back_populates='user')
    loans: Mapped[list['Loans']] = relationship('Loans', back_populates='users')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='user')
    sanctions_screening: Mapped[list['SanctionsScreening']] = relationship('SanctionsScreening', back_populates='user')
    tontines: Mapped[list['Tontines']] = relationship('Tontines', back_populates='users')
    user_devices: Mapped[list['UserDevices']] = relationship('UserDevices', back_populates='user')
    wallets: Mapped[list['Wallets']] = relationship('Wallets', back_populates='user')
    merchants: Mapped[Optional['Merchants']] = relationship('Merchants', uselist=False, back_populates='user')
    tontine_members: Mapped[list['TontineMembers']] = relationship('TontineMembers', back_populates='user')
    transactions: Mapped[list['Transactions']] = relationship('Transactions', back_populates='users')
    aml_events: Mapped[list['AmlEvents']] = relationship('AmlEvents', back_populates='user')
    disputes: Mapped[list['Disputes']] = relationship('Disputes', back_populates='users')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='users')
    tontine_contributions: Mapped[list['TontineContributions']] = relationship('TontineContributions', back_populates='user')
    tontine_payouts: Mapped[list['TontinePayouts']] = relationship('TontinePayouts', back_populates='beneficiary')


class WebhookEvents(Base):
    __tablename__ = 'webhook_events'
    __table_args__ = (
        ForeignKeyConstraint(['webhook_id'], ['paylink.webhooks.webhook_id'], ondelete='CASCADE', name='webhook_events_webhook_id_fkey'),
        PrimaryKeyConstraint('event_id', name='webhook_events_pkey'),
        {'schema': 'paylink'}
    )

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    status: Mapped[str] = mapped_column(Enum('queued', 'delivered', 'failed', 'disabled', name='webhook_status', schema='paylink'), nullable=False, server_default=text("'queued'::paylink.webhook_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    last_attempt_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    webhook: Mapped['Webhooks'] = relationship('Webhooks', back_populates='webhook_events')


class Agents(Base):
    __tablename__ = 'agents'
    __table_args__ = (
        ForeignKeyConstraint(['country_code'], ['paylink.countries.country_code'], name='agents_country_code_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='agents_user_id_fkey'),
        PrimaryKeyConstraint('agent_id', name='agents_pkey'),
        UniqueConstraint('user_id', name='agents_user_id_key'),
        {'schema': 'paylink'}
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    countries: Mapped['Countries'] = relationship('Countries', back_populates='agents')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='agents')
    agent_locations: Mapped[list['AgentLocations']] = relationship('AgentLocations', back_populates='agent')


class KycDocuments(Base):
    __tablename__ = 'kyc_documents'
    __table_args__ = (
        ForeignKeyConstraint(['reviewer_user'], ['paylink.users.user_id'], name='kyc_documents_reviewer_user_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='kyc_documents_user_id_fkey'),
        PrimaryKeyConstraint('kyc_id', name='kyc_documents_pkey'),
        Index('idx_kyc_user', 'user_id'),
        {'schema': 'paylink'}
    )

    kyc_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    doc_type: Mapped[str] = mapped_column(Enum('national_id', 'passport', 'residence_permit', 'driver_license', 'utility_bill', 'student_card', 'other', name='document_type', schema='paylink'), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    doc_number: Mapped[Optional[str]] = mapped_column(Text)
    issued_country: Mapped[Optional[str]] = mapped_column(CHAR(2))
    expires_on: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reviewer_user: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[reviewer_user], back_populates='kyc_documents')
    user: Mapped['Users'] = relationship('Users', foreign_keys=[user_id], back_populates='kyc_documents_')


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


class LimitUsage(Base):
    __tablename__ = 'limit_usage'
    __table_args__ = (
        ForeignKeyConstraint(['limit_id'], ['paylink.limits.limit_id'], ondelete='CASCADE', name='limit_usage_limit_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='limit_usage_user_id_fkey'),
        PrimaryKeyConstraint('usage_id', name='limit_usage_pkey'),
        UniqueConstraint('user_id', 'limit_id', 'period_start', name='limit_usage_user_id_limit_id_period_start_key'),
        {'schema': 'paylink'}
    )

    usage_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    limit_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    tx_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False, server_default=text('0'))

    limit: Mapped['Limits'] = relationship('Limits', back_populates='limit_usage')
    user: Mapped['Users'] = relationship('Users', back_populates='limit_usage')


class Loans(Base):
    __tablename__ = 'loans'
    __table_args__ = (
        ForeignKeyConstraint(['borrower_user'], ['paylink.users.user_id'], ondelete='CASCADE', name='loans_borrower_user_fkey'),
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='loans_currency_code_fkey'),
        PrimaryKeyConstraint('loan_id', name='loans_pkey'),
        {'schema': 'paylink'}
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    borrower_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    principal: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    apr_percent: Mapped[decimal.Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Enum('draft', 'active', 'in_arrears', 'repaid', 'written_off', name='loan_status', schema='paylink'), nullable=False, server_default=text("'draft'::paylink.loan_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    risk_level: Mapped[Optional[str]] = mapped_column(Enum('low', 'medium', 'high', 'critical', name='risk_level', schema='paylink'), server_default=text("'low'::paylink.risk_level"))

    users: Mapped['Users'] = relationship('Users', back_populates='loans')
    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='loans')
    loan_repayments: Mapped[list['LoanRepayments']] = relationship('LoanRepayments', back_populates='loan')


class Notifications(Base):
    __tablename__ = 'notifications'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='notifications_user_id_fkey'),
        PrimaryKeyConstraint('notification_id', name='notifications_pkey'),
        {'schema': 'paylink'}
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    subject: Mapped[Optional[str]] = mapped_column(Text)
    message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB)

    user: Mapped['Users'] = relationship('Users', back_populates='notifications')


class ReconFiles(Base):
    __tablename__ = 'recon_files'
    __table_args__ = (
        ForeignKeyConstraint(['provider_account_id'], ['paylink.provider_accounts.provider_account_id'], name='recon_files_provider_account_id_fkey'),
        PrimaryKeyConstraint('recon_id', name='recon_files_pkey'),
        {'schema': 'paylink'}
    )

    recon_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    provider_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    parsed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    provider_account: Mapped['ProviderAccounts'] = relationship('ProviderAccounts', back_populates='recon_files')
    recon_lines: Mapped[list['ReconLines']] = relationship('ReconLines', back_populates='recon')


class SanctionsScreening(Base):
    __tablename__ = 'sanctions_screening'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='sanctions_screening_user_id_fkey'),
        PrimaryKeyConstraint('screening_id', name='sanctions_screening_pkey'),
        {'schema': 'paylink'}
    )

    screening_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    provider: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    user: Mapped['Users'] = relationship('Users', back_populates='sanctions_screening')


class Settlements(Base):
    __tablename__ = 'settlements'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='settlements_currency_code_fkey'),
        ForeignKeyConstraint(['provider_account_id'], ['paylink.provider_accounts.provider_account_id'], name='settlements_provider_account_id_fkey'),
        PrimaryKeyConstraint('settlement_id', name='settlements_pkey'),
        {'schema': 'paylink'}
    )

    settlement_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'::text"))
    provider_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    executed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='settlements')
    provider_account: Mapped[Optional['ProviderAccounts']] = relationship('ProviderAccounts', back_populates='settlements')


class Tontines(Base):
    __tablename__ = 'tontines'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='tontines_currency_code_fkey'),
        ForeignKeyConstraint(['owner_user'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontines_owner_user_fkey'),
        PrimaryKeyConstraint('tontine_id', name='tontines_pkey'),
        {'schema': 'paylink'}
    )

    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    owner_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    periodicity_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('30'))
    status: Mapped[str] = mapped_column(Enum('draft', 'active', 'paused', 'completed', 'cancelled', name='tontine_status', schema='paylink'), nullable=False, server_default=text("'draft'::paylink.tontine_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='tontines')
    users: Mapped['Users'] = relationship('Users', back_populates='tontines')
    tontine_members: Mapped[list['TontineMembers']] = relationship('TontineMembers', back_populates='tontine')
    tontine_contributions: Mapped[list['TontineContributions']] = relationship('TontineContributions', back_populates='tontine')
    tontine_payouts: Mapped[list['TontinePayouts']] = relationship('TontinePayouts', back_populates='tontine')


class UserAuth(Users):
    __tablename__ = 'user_auth'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='user_auth_user_id_fkey'),
        PrimaryKeyConstraint('user_id', name='user_auth_pkey'),
        {'schema': 'paylink'}
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class UserDevices(Base):
    __tablename__ = 'user_devices'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='user_devices_user_id_fkey'),
        PrimaryKeyConstraint('device_id', name='user_devices_pkey'),
        {'schema': 'paylink'}
    )

    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    device_fingerprint: Mapped[Optional[str]] = mapped_column(Text)
    push_token: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped['Users'] = relationship('Users', back_populates='user_devices')


class Wallets(Base):
    __tablename__ = 'wallets'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='wallets_currency_code_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='SET NULL', name='wallets_user_id_fkey'),
        PrimaryKeyConstraint('wallet_id', name='wallets_pkey'),
        UniqueConstraint('user_id', 'currency_code', 'type', name='wallets_user_id_currency_code_type_key'),
        Index('idx_wallets_currency', 'currency_code'),
        Index('idx_wallets_user', 'user_id'),
        {'schema': 'paylink'}
    )

    wallet_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    type: Mapped[str] = mapped_column(Enum('consumer', 'agent', 'merchant', 'settlement', 'reserve', name='wallet_type', schema='paylink'), nullable=False, server_default=text("'consumer'::paylink.wallet_type"))
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    available: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False, server_default=text('0'))
    pending: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='wallets')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='wallets')
    merchants: Mapped[list['Merchants']] = relationship('Merchants', back_populates='wallets')
    transactions: Mapped[list['Transactions']] = relationship('Transactions', foreign_keys='[Transactions.receiver_wallet]', back_populates='wallets')
    transactions_: Mapped[list['Transactions']] = relationship('Transactions', foreign_keys='[Transactions.sender_wallet]', back_populates='wallets_')


class AgentLocations(Base):
    __tablename__ = 'agent_locations'
    __table_args__ = (
        ForeignKeyConstraint(['agent_id'], ['paylink.agents.agent_id'], ondelete='CASCADE', name='agent_locations_agent_id_fkey'),
        PrimaryKeyConstraint('location_id', name='agent_locations_pkey'),
        {'schema': 'paylink'}
    )

    location_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    label: Mapped[Optional[str]] = mapped_column(Text)
    lat: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    lng: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    address: Mapped[Optional[str]] = mapped_column(Text)

    agent: Mapped['Agents'] = relationship('Agents', back_populates='agent_locations')


class Merchants(Base):
    __tablename__ = 'merchants'
    __table_args__ = (
        ForeignKeyConstraint(['settlement_wallet'], ['paylink.wallets.wallet_id'], name='merchants_settlement_wallet_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='merchants_user_id_fkey'),
        PrimaryKeyConstraint('merchant_id', name='merchants_pkey'),
        UniqueConstraint('user_id', name='merchants_user_id_key'),
        {'schema': 'paylink'}
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    tax_id: Mapped[Optional[str]] = mapped_column(Text)
    settlement_wallet: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    wallets: Mapped[Optional['Wallets']] = relationship('Wallets', back_populates='merchants')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='merchants')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='merchant')


class TontineMembers(Base):
    __tablename__ = 'tontine_members'
    __table_args__ = (
        ForeignKeyConstraint(['tontine_id'], ['paylink.tontines.tontine_id'], ondelete='CASCADE', name='tontine_members_tontine_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontine_members_user_id_fkey'),
        PrimaryKeyConstraint('tontine_id', 'user_id', name='tontine_members_pkey'),
        UniqueConstraint('tontine_id', 'join_order', name='tontine_members_tontine_id_join_order_key'),
        {'schema': 'paylink'}
    )

    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    join_order: Mapped[int] = mapped_column(Integer, nullable=False)

    tontine: Mapped['Tontines'] = relationship('Tontines', back_populates='tontine_members')
    user: Mapped['Users'] = relationship('Users', back_populates='tontine_members')


class Transactions(Base):
    __tablename__ = 'transactions'
    __table_args__ = (
        CheckConstraint('amount > 0::numeric', name='transactions_amount_check'),
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='transactions_currency_code_fkey'),
        ForeignKeyConstraint(['initiated_by'], ['paylink.users.user_id'], name='transactions_initiated_by_fkey'),
        ForeignKeyConstraint(['receiver_wallet'], ['paylink.wallets.wallet_id'], name='transactions_receiver_wallet_fkey'),
        ForeignKeyConstraint(['sender_wallet'], ['paylink.wallets.wallet_id'], name='transactions_sender_wallet_fkey'),
        PrimaryKeyConstraint('tx_id', name='transactions_pkey'),
        Index('idx_tx_receiver', 'receiver_wallet'),
        Index('idx_tx_sender', 'sender_wallet'),
        Index('idx_tx_status', 'status'),
        {'schema': 'paylink'}
    )

    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    channel: Mapped[str] = mapped_column(Enum('mobile_money', 'bank', 'card', 'cash', 'internal', 'bank_transfer', name='tx_channel', schema='paylink'), nullable=False)
    status: Mapped[str] = mapped_column(Enum('initiated', 'pending', 'succeeded', 'failed', 'cancelled', 'reversed', 'chargeback', name='tx_status', schema='paylink'), nullable=False, server_default=text("'initiated'::paylink.tx_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    initiated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    sender_wallet: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    receiver_wallet: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    external_ref: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='transactions')
    users: Mapped[Optional['Users']] = relationship('Users', back_populates='transactions')
    wallets: Mapped[Optional['Wallets']] = relationship('Wallets', foreign_keys=[receiver_wallet], back_populates='transactions')
    wallets_: Mapped[Optional['Wallets']] = relationship('Wallets', foreign_keys=[sender_wallet], back_populates='transactions_')
    aml_events: Mapped[list['AmlEvents']] = relationship('AmlEvents', back_populates='tx')
    disputes: Mapped[list['Disputes']] = relationship('Disputes', back_populates='tx')
    fx_conversions: Mapped[list['FxConversions']] = relationship('FxConversions', back_populates='tx')
    loan_repayments: Mapped[list['LoanRepayments']] = relationship('LoanRepayments', back_populates='tx')
    payment_instructions: Mapped[list['PaymentInstructions']] = relationship('PaymentInstructions', back_populates='tx')
    recon_lines: Mapped[list['ReconLines']] = relationship('ReconLines', back_populates='transactions')
    tontine_contributions: Mapped[list['TontineContributions']] = relationship('TontineContributions', back_populates='tx')
    tontine_payouts: Mapped[list['TontinePayouts']] = relationship('TontinePayouts', back_populates='tx')
    bill_payments: Mapped[list['BillPayments']] = relationship('BillPayments', back_populates='tx')


class AmlEvents(Base):
    __tablename__ = 'aml_events'
    __table_args__ = (
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='aml_events_tx_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], name='aml_events_user_id_fkey'),
        PrimaryKeyConstraint('aml_id', name='aml_events_pkey'),
        {'schema': 'paylink'}
    )

    aml_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Enum('low', 'medium', 'high', 'critical', name='risk_level', schema='paylink'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='aml_events')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='aml_events')


class Disputes(Base):
    __tablename__ = 'disputes'
    __table_args__ = (
        ForeignKeyConstraint(['opened_by'], ['paylink.users.user_id'], name='disputes_opened_by_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], ondelete='CASCADE', name='disputes_tx_id_fkey'),
        PrimaryKeyConstraint('dispute_id', name='disputes_pkey'),
        {'schema': 'paylink'}
    )

    dispute_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(Enum('opened', 'investigating', 'won', 'lost', 'closed', name='dispute_status', schema='paylink'), nullable=False, server_default=text("'opened'::paylink.dispute_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    opened_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence_url: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[Optional['Users']] = relationship('Users', back_populates='disputes')
    tx: Mapped['Transactions'] = relationship('Transactions', back_populates='disputes')


class FxConversions(Base):
    __tablename__ = 'fx_conversions'
    __table_args__ = (
        ForeignKeyConstraint(['from_currency'], ['paylink.currencies.currency_code'], name='fx_conversions_from_currency_fkey'),
        ForeignKeyConstraint(['to_currency'], ['paylink.currencies.currency_code'], name='fx_conversions_to_currency_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], ondelete='CASCADE', name='fx_conversions_tx_id_fkey'),
        PrimaryKeyConstraint('conversion_id', name='fx_conversions_pkey'),
        {'schema': 'paylink'}
    )

    conversion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate_used: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee_fx_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    currencies: Mapped['Currencies'] = relationship('Currencies', foreign_keys=[from_currency], back_populates='fx_conversions')
    currencies_: Mapped['Currencies'] = relationship('Currencies', foreign_keys=[to_currency], back_populates='fx_conversions_')
    tx: Mapped['Transactions'] = relationship('Transactions', back_populates='fx_conversions')


class Invoices(Base):
    __tablename__ = 'invoices'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='invoices_currency_code_fkey'),
        ForeignKeyConstraint(['customer_user'], ['paylink.users.user_id'], name='invoices_customer_user_fkey'),
        ForeignKeyConstraint(['merchant_id'], ['paylink.merchants.merchant_id'], ondelete='CASCADE', name='invoices_merchant_id_fkey'),
        PrimaryKeyConstraint('invoice_id', name='invoices_pkey'),
        Index('idx_invoices_merchant', 'merchant_id', 'status'),
        {'schema': 'paylink'}
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unpaid'::text"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    customer_user: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='invoices')
    users: Mapped[Optional['Users']] = relationship('Users', back_populates='invoices')
    merchant: Mapped['Merchants'] = relationship('Merchants', back_populates='invoices')
    bill_payments: Mapped[list['BillPayments']] = relationship('BillPayments', back_populates='invoice')


class LoanRepayments(Base):
    __tablename__ = 'loan_repayments'
    __table_args__ = (
        ForeignKeyConstraint(['loan_id'], ['paylink.loans.loan_id'], ondelete='CASCADE', name='loan_repayments_loan_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='loan_repayments_tx_id_fkey'),
        PrimaryKeyConstraint('repayment_id', name='loan_repayments_pkey'),
        {'schema': 'paylink'}
    )

    repayment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    loan_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    paid_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6), server_default=text('0'))
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    loan: Mapped['Loans'] = relationship('Loans', back_populates='loan_repayments')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='loan_repayments')


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
    direction: Mapped[str] = mapped_column(Enum('credit', 'debit', name='tx_direction', schema='paylink'), nullable=False)
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


class ReconLines(Base):
    __tablename__ = 'recon_lines'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='recon_lines_currency_code_fkey'),
        ForeignKeyConstraint(['matched_tx'], ['paylink.transactions.tx_id'], name='recon_lines_matched_tx_fkey'),
        ForeignKeyConstraint(['recon_id'], ['paylink.recon_files.recon_id'], ondelete='CASCADE', name='recon_lines_recon_id_fkey'),
        PrimaryKeyConstraint('recon_line_id', name='recon_lines_pkey'),
        Index('idx_recon_lines_ref', 'external_ref'),
        {'schema': 'paylink'}
    )

    recon_line_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recon_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unmatched'::text"))
    external_ref: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6))
    currency_code: Mapped[Optional[str]] = mapped_column(CHAR(3))
    matched_tx: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    currencies: Mapped[Optional['Currencies']] = relationship('Currencies', back_populates='recon_lines')
    transactions: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='recon_lines')
    recon: Mapped['ReconFiles'] = relationship('ReconFiles', back_populates='recon_lines')


class TontineContributions(Base):
    __tablename__ = 'tontine_contributions'
    __table_args__ = (
        ForeignKeyConstraint(['tontine_id'], ['paylink.tontines.tontine_id'], ondelete='CASCADE', name='tontine_contributions_tontine_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='tontine_contributions_tx_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontine_contributions_user_id_fkey'),
        PrimaryKeyConstraint('contribution_id', name='tontine_contributions_pkey'),
        {'schema': 'paylink'}
    )

    contribution_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    paid_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    tontine: Mapped['Tontines'] = relationship('Tontines', back_populates='tontine_contributions')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='tontine_contributions')
    user: Mapped['Users'] = relationship('Users', back_populates='tontine_contributions')


class TontinePayouts(Base):
    __tablename__ = 'tontine_payouts'
    __table_args__ = (
        ForeignKeyConstraint(['beneficiary_id'], ['paylink.users.user_id'], name='tontine_payouts_beneficiary_id_fkey'),
        ForeignKeyConstraint(['tontine_id'], ['paylink.tontines.tontine_id'], ondelete='CASCADE', name='tontine_payouts_tontine_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='tontine_payouts_tx_id_fkey'),
        PrimaryKeyConstraint('payout_id', name='tontine_payouts_pkey'),
        {'schema': 'paylink'}
    )

    payout_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    beneficiary: Mapped['Users'] = relationship('Users', back_populates='tontine_payouts')
    tontine: Mapped['Tontines'] = relationship('Tontines', back_populates='tontine_payouts')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='tontine_payouts')


class BillPayments(Base):
    __tablename__ = 'bill_payments'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['paylink.invoices.invoice_id'], ondelete='CASCADE', name='bill_payments_invoice_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='bill_payments_tx_id_fkey'),
        PrimaryKeyConstraint('bill_payment_id', name='bill_payments_pkey'),
        {'schema': 'paylink'}
    )

    bill_payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    paid_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='bill_payments')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='bill_payments')
