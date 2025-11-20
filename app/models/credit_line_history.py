from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.transactions import Transactions
from app.models.users import Users


class CreditLineHistory(Base):
    __tablename__ = "credit_line_history"
    __table_args__ = {"schema": "paylink"}

    entry_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.transactions.tx_id", ondelete="SET NULL"),
    )
    amount = Column(Numeric(20, 6), nullable=False)
    credit_available_before = Column(Numeric(20, 6), nullable=False)
    credit_available_after = Column(Numeric(20, 6), nullable=False)
    description = Column(Text)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user = relationship(Users)
    transaction = relationship(Transactions)
