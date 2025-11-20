# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

from app.models.currencies import Currencies
from app.models.provideraccounts import ProviderAccounts
