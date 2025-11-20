# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LedgerJournal(Base):
    __tablename__ = 'ledger_journal'
    __table_args__ = (
        PrimaryKeyConstraint('journal_id', name='ledger_journal_pkey'),
        {'schema': 'paylink'}
    )

    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    ledger_entries: Mapped[list['LedgerEntries']] = relationship('LedgerEntries', back_populates='journal')

from app.models.ledgerentries import LedgerEntries
