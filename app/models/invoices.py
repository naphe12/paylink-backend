# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional
from uuid import UUID
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func
from sqlalchemy import Column
from sqlalchemy import ForeignKeyConstraint,PrimaryKeyConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationships , Mapped, mapped_column
import uuid
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Integer,
    TIMESTAMP,Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base  # ta base declarative (from sqlalchemy.ext.declarative import declarative_base)

from sqlalchemy import BigInteger, Boolean, CHAR, CheckConstraint, Column, Date, DateTime, Enum, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, Table, Text, UniqueConstraint, Uuid, text,SmallInteger, String, Sequence,ForeignKey
from sqlalchemy.dialects.postgresql import INTERVAL, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.core.database import Base

from sqlalchemy import Column, ForeignKey, Numeric, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from sqlalchemy import *
from app.core.database import Base
from app.core.database import Base


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

    invoice_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    merchant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unpaid'::text"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    customer_user: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='invoices')
    users: Mapped[Optional['Users']] = relationship('Users', back_populates='invoices')
    merchant: Mapped['Merchants'] = relationship('Merchants', back_populates='invoices')
    bill_payments: Mapped[list['BillPayments']] = relationship('BillPayments', back_populates='invoice')

from app.models.billpayments import BillPayments
from app.models.currencies import Currencies
from app.models.merchants import Merchants
from app.models.users import Users
