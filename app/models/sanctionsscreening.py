# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SanctionsScreening(Base):
    __tablename__ = 'sanctions_screening'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='sanctions_screening_user_id_fkey'),
        PrimaryKeyConstraint('screening_id', name='sanctions_screening_pkey'),
        {'schema': 'paylink'}
    )

    screening_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    provider: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    user: Mapped['Users'] = relationship('Users', back_populates='sanctions_screening')

from app.models.users import Users
