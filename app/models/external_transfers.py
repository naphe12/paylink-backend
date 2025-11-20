import uuid
from datetime import datetime

from sqlalchemy import (JSON, TIMESTAMP, Boolean, Column, DateTime, ForeignKey,
                        Numeric, String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from typing import Optional
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, text, DateTime
from app.core.database import Base


class ExternalTransfers(Base):
    __tablename__ = "external_transfers"
    __table_args__ = {"schema": "paylink"}  # ✅ à adapter selon ton schéma

    transfer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    partner_name = Column(Text, nullable=False)  # Lumicash, Ecocash, Enoti, etc.
    country_destination = Column(Text, nullable=False)
    recipient_name = Column(Text, nullable=False)
    recipient_phone = Column(Text, nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(5), default="EUR")

    rate = Column(Numeric(10, 4))
    local_amount = Column(Numeric(12, 2))

    credit_used = Column(Boolean, default=False)
    status = Column(String(20), default="pending")  # pending, success, failed
    reference_code = Column(String(50), unique=True)

    
    metadata_ : Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    processed_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=True)

    
    processed_at = Column(DateTime(timezone=True),default=datetime.utcnow)
    # Relation avec User
    # ✅ Relationships avec foreign_keys spécifié
    initiator = relationship(
        "Users",
        foreign_keys=[user_id],
        back_populates="external_transfers_initiated",
    )
    processor = relationship(
        "Users",
        foreign_keys=[processed_by],
        back_populates="external_transfers_processed",
    )
