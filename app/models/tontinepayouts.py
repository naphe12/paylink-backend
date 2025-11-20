# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

    from app.models.tontines import Tontines
    from app.models.transactions import Transactions
    from app.models.users import Users
