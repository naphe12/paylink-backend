# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AmlEvents(Base):
    __tablename__ = 'aml_events'
    __table_args__ = (
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='aml_events_tx_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], name='aml_events_user_id_fkey'),
        PrimaryKeyConstraint('aml_id', name='aml_events_pkey'),
        {'schema': 'paylink'}
    )

    aml_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Enum('low', 'medium', 'high', 'critical', name='risk_level', schema='paylink'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='aml_events')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='aml_events')

from app.models.transactions import Transactions
from app.models.users import Users
