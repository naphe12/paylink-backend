# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

from app.models.currencies import Currencies
from app.models.limitusage import LimitUsage
