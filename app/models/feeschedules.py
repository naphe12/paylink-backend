# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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
from app.models.currencies import Currencies
from app.models.providers import Providers
