import decimal
import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class CreditLinePayments(Base):
    __tablename__ = "credit_line_payments"
    __table_args__ = {"schema": "paylink"}

    payment_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    credit_line_id = Column(UUID(as_uuid=True), ForeignKey("paylink.credit_lines.credit_line_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    amount = Column(Numeric(15, 2), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    amount_eur = Column(Numeric(15, 2))
    balance_before = Column(Numeric(12, 2))
    balance_after = Column(Numeric(12, 2))

    legacy_payment_id = Column(BigInteger)
    legacy_sending_id = Column(BigInteger)

    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    credit_line = relationship("CreditLines", back_populates="payments")
    user = relationship("Users")
