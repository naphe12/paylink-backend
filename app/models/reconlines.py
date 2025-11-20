# Auto-generated from database schema
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReconLines(Base):
    __tablename__ = 'recon_lines'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='recon_lines_currency_code_fkey'),
        ForeignKeyConstraint(['matched_tx'], ['paylink.transactions.tx_id'], name='recon_lines_matched_tx_fkey'),
        ForeignKeyConstraint(['recon_id'], ['paylink.recon_files.recon_id'], ondelete='CASCADE', name='recon_lines_recon_id_fkey'),
        PrimaryKeyConstraint('recon_line_id', name='recon_lines_pkey'),
        Index('idx_recon_lines_ref', 'external_ref'),
        {'schema': 'paylink'}
    )

    recon_line_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recon_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unmatched'::text"))
    external_ref: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6))
    currency_code: Mapped[Optional[str]] = mapped_column(CHAR(3))
    matched_tx: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    currencies: Mapped[Optional['Currencies']] = relationship('Currencies', back_populates='recon_lines')
    transactions: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='recon_lines')
    recon: Mapped['ReconFiles'] = relationship('ReconFiles', back_populates='recon_lines')

from app.models.currencies import Currencies
from app.models.reconfiles import ReconFiles
from app.models.transactions import Transactions
