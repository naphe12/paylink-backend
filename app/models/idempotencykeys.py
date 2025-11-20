# Auto-generated from database schema
# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

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
from sqlalchemy.orm import relationship
import uuid
import enum
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base
from sqlalchemy import *

class IdempotencyKeys(Base):
    __tablename__ = 'idempotency_keys'
    __table_args__ = (
        PrimaryKeyConstraint('key_id', name='idempotency_keys_pkey'),
        UniqueConstraint('client_key', name='idempotency_keys_client_key_key'),
        {'schema': 'paylink'}
    )

    key_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    client_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
