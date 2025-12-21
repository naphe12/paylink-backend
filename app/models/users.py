# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

from sqlalchemy import Column, String, Enum, Integer

import enum



from sqlalchemy import (
    Column, String, Date, Text, Numeric, ForeignKey,
    TIMESTAMP, Integer, Enum, Date
)
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

import enum




# app/models/users.py
import enum
import uuid
from typing import Optional
from sqlalchemy import (
    Column, Text, Numeric, Enum, Boolean, Date, ForeignKeyConstraint,
    PrimaryKeyConstraint, UniqueConstraint, Index, TIMESTAMP, ForeignKey,
    text
)
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped

from app.core.database import Base


class UserStatus(enum.Enum):
    pending = "pending"
    active = "active"
    frozen = "frozen"
    closed = "closed"
    suspended="suspended"


class KycStatus(enum.Enum):
    unverified = "unverified"
    reviewing = "reviewing"
    verified = "verified"
    rejected = "rejected"


class UserRole(enum.Enum):
    client = "client"
    agent = "agent"
    admin = "admin"
    user = "user"


class Users(Base):
    __tablename__ = "users"
    __table_args__ = (
        ForeignKeyConstraint(["country_code"], ["paylink.countries.country_code"]),
        ForeignKeyConstraint(["referred_by"], ["paylink.users.user_id"]),
        PrimaryKeyConstraint("user_id"),
        UniqueConstraint("email"),
        UniqueConstraint("phone_e164"),
        Index("idx_users_country", "country_code"),
        Index("idx_users_phone", "phone_e164"),
        {"schema": "paylink"},
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True,server_default=text('gen_random_uuid()'))
    full_name = Column(Text, nullable=False)
    username = Column(Text, nullable=True)
    email = Column(CITEXT, unique=True)
    phone_e164 = Column(CITEXT, unique=True)
    country_code = Column(Text)
    #status = Column(Enum(UserStatus), nullable=False, default=UserStatus.pending)
    status = Column(Enum("pending", "active", "frozen", "closed","suspended", name="user_status", schema="paylink"), nullable=False)
    kyc_status  = Column(Enum("unverified", "verified", "reviewing", "rejected", name="kyc_status", schema="paylink"), nullable=False)
    referred_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    role  = Column(Enum("client", "user", "agent", "admin", name="user_role", schema="paylink"), nullable=False)
    external_transfers_blocked = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True))    
    credit_limit = Column(Numeric(12, 2), server_default='0.0')
    credit_used = Column(Numeric(12, 2), server_default='0.0')
    legal_name = Column(Text)
    birth_date = Column(Date)
    national_id_number = Column(Text)
    kyc_document_type = Column(Text)
    kyc_document_front_url = Column(Text)
    kyc_document_back_url = Column(Text)
    selfie_url = Column(Text)
    kyc_reject_reason = Column(Text)
    kyc_tier = Column(SmallInteger, server_default='0')
    daily_limit = Column(Numeric, server_default='30000')
    monthly_limit = Column(Numeric, server_default='30000')
    used_daily = Column(Numeric, server_default='0')
    used_monthly = Column(Numeric, server_default='0')
    last_reset = Column(Date, server_default=func.current_date())
    risk_score = Column(Integer, nullable=False, server_default='0')  
    kyc_submitted_at=Column(TIMESTAMP(timezone=True), server_default=func.now())
    paytag = Column(CITEXT)
    email_verified = Column(Boolean, nullable=False, server_default=text("false"))
    email_verified_at = Column(TIMESTAMP(timezone=True))

    # ✅ Relation inverse correcte Transactions <-> Users
    transactions_initiated = relationship(
        "Transactions",
        foreign_keys="Transactions.initiated_by",
        back_populates="initiator",
    )
    credit_line_events = relationship("CreditLineEvents", back_populates="user")

    # ✅ Relation wallet
    # (removed duplicate untyped wallets relationship; see typed one below)
    agents: Mapped[Optional['Agents']] = relationship('Agents', uselist=False, back_populates='user')
    countries: Mapped[Optional['Countries']] = relationship('Countries', back_populates='users')
    
    
    kyc_documents: Mapped[list['KycDocuments']] = relationship('KycDocuments', foreign_keys='[KycDocuments.reviewer_user]', back_populates='users')
    kyc_documents_: Mapped[list['KycDocuments']] = relationship('KycDocuments', foreign_keys='[KycDocuments.user_id]', back_populates='user')
    limit_usage: Mapped[list['LimitUsage']] = relationship('LimitUsage', back_populates='user')
    loans: Mapped[list['Loans']] = relationship('Loans', back_populates='users')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='user')
    security_events: Mapped[list['SecurityEvents']] = relationship('SecurityEvents', back_populates='user')
    sanctions_screening: Mapped[list['SanctionsScreening']] = relationship('SanctionsScreening', back_populates='user')
    credit_lines: Mapped[list['CreditLines']] = relationship('CreditLines', back_populates='user')
    client_balance_events: Mapped[list['ClientBalanceEvents']] = relationship('ClientBalanceEvents', back_populates='user')
    tontines: Mapped[list['Tontines']] = relationship('Tontines', back_populates='users')
    user_devices: Mapped[list['UserDevices']] = relationship('UserDevices', back_populates='user')
    wallets: Mapped[list['Wallets']] = relationship('Wallets', back_populates='user')
    merchants: Mapped[Optional['Merchants']] = relationship('Merchants', uselist=False, back_populates='user')
    tontine_members: Mapped[list['TontineMembers']] = relationship('TontineMembers', back_populates='user')
    aml_events: Mapped[list['AmlEvents']] = relationship('AmlEvents', back_populates='user')
    disputes: Mapped[list['Disputes']] = relationship('Disputes', back_populates='users')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='users')
    tontine_contributions: Mapped[list['TontineContributions']] = relationship('TontineContributions', back_populates='user')
    tontine_payouts: Mapped[list['TontinePayouts']] = relationship('TontinePayouts', back_populates='beneficiary')
    agent_commissions: Mapped[list['AgentCommissions']] = relationship('AgentCommissions', back_populates='agent')
    wallet_transactions: Mapped[list['WalletTransactions']] = relationship('WalletTransactions', back_populates='user')
    external_transfers_initiated: Mapped[list['ExternalTransfers']] = relationship(
        'ExternalTransfers',
        foreign_keys='[ExternalTransfers.user_id]',
        back_populates='initiator'
    )
    external_transfers_processed: Mapped[list['ExternalTransfers']] = relationship(
        'ExternalTransfers',
        foreign_keys='[ExternalTransfers.processed_by]',
        back_populates='processor'
    )
    
    bonus_history = relationship("BonusHistory", back_populates="user", cascade="all, delete")
    auth: Mapped[Optional["UserAuth"]] = relationship(    "UserAuth",    back_populates="user",    uselist=False,    cascade="all, delete-orphan")
    mobilemoney_requests: Mapped[list['MobileMoneyRequests']] = relationship('MobileMoneyRequests', back_populates='user')


from app.models.agents import Agents
from app.models.amlevents import AmlEvents
from app.models.countries import Countries
from app.models.disputes import Disputes
from app.models.invoices import Invoices
from app.models.kycdocuments import KycDocuments
from app.models.limitusage import LimitUsage
from app.models.loans import Loans
from app.models.merchants import Merchants
from app.models.notifications import Notifications
from app.models.sanctionsscreening import SanctionsScreening
from app.models.tontinecontributions import TontineContributions
from app.models.tontinemembers import TontineMembers
from app.models.tontinepayouts import TontinePayouts
from app.models.tontines import Tontines
from app.models.user_auth import UserAuth
from app.models.userdevices import UserDevices
from app.models.wallets import Wallets
from app.models.security_events import SecurityEvents
from app.models.agent_transactions import AgentTransactions
from app.models.agent_commissions import AgentCommissions
from app.models.external_transfers import ExternalTransfers
from app.models.wallet_transactions import WalletTransactions
from app.models.mobilemoney_requests import MobileMoneyRequests
