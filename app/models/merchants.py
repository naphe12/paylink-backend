# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

    wallet = relationship("Wallets", back_populates="merchants")

    user: Mapped[Optional['Users']] = relationship('Users', back_populates='merchants')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='merchant')

from app.models.invoices import Invoices
from app.models.users import Users
from app.models.wallets import Wallets
