from typing import Optional
import datetime
import decimal
import uuid
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Integer,
    TIMESTAMP,Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base  # ta base declarative (from sqlalchemy.ext.declarative import declarative_base)

from sqlalchemy import BigInteger, Boolean, CHAR, CheckConstraint, Column, Date, DateTime, Enum, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, Table, Text, UniqueConstraint, Uuid, text,SmallInteger, String, Sequence,ForeignKey
from sqlalchemy.dialects.postgresql import INTERVAL, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.core.database import Base

from sqlalchemy import Column, ForeignKey, Numeric, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from sqlalchemy import *
from app.core.database import Base


class KycDocuments(Base):
    __tablename__ = 'kyc_documents'
    __table_args__ = (
        ForeignKeyConstraint(['reviewer_user'], ['paylink.users.user_id'], name='kyc_documents_reviewer_user_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='kyc_documents_user_id_fkey'),
        PrimaryKeyConstraint('kyc_id', name='kyc_documents_pkey'),
        Index('idx_kyc_user', 'user_id'),
        {'schema': 'paylink'}
    )

    kyc_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    doc_type: Mapped[str] = mapped_column(Enum('national_id', 'passport', 'residence_permit', 'driver_license', 'utility_bill', 'student_card', 'other', name='document_type', schema='paylink'), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    doc_number: Mapped[Optional[str]] = mapped_column(Text)
    issued_country: Mapped[Optional[str]] = mapped_column(CHAR(2))
    expires_on: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reviewer_user: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[reviewer_user], back_populates='kyc_documents')
    user: Mapped['Users'] = relationship('Users', foreign_keys=[user_id], back_populates='kyc_documents_')
from app.models.users import Users
