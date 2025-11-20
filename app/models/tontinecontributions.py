# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

import enum

class ContributionStatus(enum.Enum):
    paid = "paid"
    unpaid = "unpaid"
    promised = "promised"
    pending = "pending"
    def __str__(self):
        return self.value



class TontineContributions(Base):
    __tablename__ = 'tontine_contributions'
    __table_args__ = (
        ForeignKeyConstraint(['tontine_id'], ['paylink.tontines.tontine_id'], ondelete='CASCADE', name='tontine_contributions_tontine_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='tontine_contributions_tx_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontine_contributions_user_id_fkey'),
        PrimaryKeyConstraint('contribution_id', name='tontine_contributions_pkey'),
        {'schema': 'paylink'}
    )

    contribution_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    paid_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    #status = Column(Enum(ContributionStatus, name="contribution_status", schema="paylink"), nullable=False)
    status: Mapped[str] = mapped_column(Enum('paid', 'unpaid', 'promised', 'pending', name='contribution_status', schema='paylink'), nullable=False, server_default=text("'pending'::paylink.contribution_status"))
    tontine: Mapped['Tontines'] = relationship('Tontines', back_populates='tontine_contributions')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='tontine_contributions')
    user: Mapped['Users'] = relationship('Users', back_populates='tontine_contributions')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

from app.models.tontines import Tontines
from app.models.transactions import Transactions
from app.models.users import Users
