import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class CreditLineEvents(Base):
    __tablename__ = "credit_line_events"
    __table_args__ = {"schema": "paylink"}

    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    credit_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.credit_lines.credit_line_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_delta = Column(Numeric(12, 2), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    old_limit = Column(Numeric(12, 2))
    new_limit = Column(Numeric(12, 2))
    operation_code = Column(Integer)
    status = Column(Text)
    source = Column(Text, server_default=text("'legacy'"))
    legacy_sendlog_id = Column(BigInteger)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    user = relationship("Users", back_populates="credit_line_events")
    credit_line = relationship("CreditLines", back_populates="events")
