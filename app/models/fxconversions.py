# Auto-generated from database schema
import datetime
import decimal
import uuid

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

from app.models.currencies import Currencies
from app.models.transactions import Transactions
