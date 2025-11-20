# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationships
# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional
from sqlalchemy import *
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func
from sqlalchemy import Column
from sqlalchemy import ForeignKeyConstraint,PrimaryKeyConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationships , Mapped, mapped_column
import uuid
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationships
import uuid
import enum
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base

from app.core.database import Base


class LedgerAccounts(Base):
    __tablename__ = 'ledger_accounts'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='ledger_accounts_currency_code_fkey'),
        PrimaryKeyConstraint('account_id', name='ledger_accounts_pkey'),
        UniqueConstraint('code', name='ledger_accounts_code_key'),
        {'schema': 'paylink'}
    )

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='ledger_accounts')
    ledger_entries: Mapped[list['LedgerEntries']] = relationship('LedgerEntries', back_populates='account')

from app.models.currencies import Currencies
from app.models.ledgerentries import LedgerEntries
