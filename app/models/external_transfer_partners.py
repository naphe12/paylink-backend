import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ExternalTransferPartners(Base):
    __tablename__ = "external_transfer_partners"
    __table_args__ = {"schema": "paylink"}

    partner_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_name = Column(Text, nullable=False, unique=True)
    provider = Column(String(30), nullable=False, default="internal")
    is_active = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

