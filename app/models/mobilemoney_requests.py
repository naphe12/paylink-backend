from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class MobileMoneyRequests(Base):
    __tablename__ = "mobilemoney_requests"
    __table_args__ = {"schema": "paylink"}

    request_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=False)
    tx_id = Column(UUID(as_uuid=True), ForeignKey("paylink.transactions.tx_id"))
    provider = Column(String(50), nullable=False)
    phone = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(String(20), nullable=False)  # cashin / cashout
    status = Column(String(20), nullable=False, server_default="initiated")  # initiated/pending/success/failed
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text)
    next_retry_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    user = relationship("Users", back_populates="mobilemoney_requests")
    transaction = relationship("Transactions")
