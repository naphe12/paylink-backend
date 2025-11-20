# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReconFiles(Base):
    __tablename__ = 'recon_files'
    __table_args__ = (
        ForeignKeyConstraint(['provider_account_id'], ['paylink.provider_accounts.provider_account_id'], name='recon_files_provider_account_id_fkey'),
        PrimaryKeyConstraint('recon_id', name='recon_files_pkey'),
        {'schema': 'paylink'}
    )

    recon_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    provider_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    parsed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    provider_account: Mapped['ProviderAccounts'] = relationship('ProviderAccounts', back_populates='recon_files')
    recon_lines: Mapped[list['ReconLines']] = relationship('ReconLines', back_populates='recon')

from app.models.provideraccounts import ProviderAccounts
from app.models.reconlines import ReconLines
