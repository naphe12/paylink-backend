# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

from app.models.currencies import Currencies
from app.models.paymentinstructions import PaymentInstructions
from app.models.providers import Providers
from app.models.reconfiles import ReconFiles
from app.models.settlements import Settlements
