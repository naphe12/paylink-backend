# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional
from sqlalchemy import *
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func


from sqlalchemy.orm import Mapped, mapped_column, relationships

from app.core.database import Base


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

from app.models.currencies import Currencies
from app.models.providers import Providers
