# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Disputes(Base):
    __tablename__ = 'disputes'
    __table_args__ = (
        ForeignKeyConstraint(['opened_by'], ['paylink.users.user_id'], name='disputes_opened_by_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], ondelete='CASCADE', name='disputes_tx_id_fkey'),
        PrimaryKeyConstraint('dispute_id', name='disputes_pkey'),
        {'schema': 'paylink'}
    )

    dispute_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(Enum('opened', 'investigating', 'won', 'lost', 'closed', name='dispute_status', schema='paylink'), nullable=False, server_default=text("'opened'::paylink.dispute_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    opened_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence_url: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[Optional['Users']] = relationship('Users', back_populates='disputes')
    tx: Mapped['Transactions'] = relationship('Transactions', back_populates='disputes')
from app.models.transactions import Transactions
from app.models.users import Users
