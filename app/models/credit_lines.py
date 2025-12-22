from datetime import datetime

from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.credit_line_payments import CreditLinePayments
from app.models.credit_line_events import CreditLineEvents
from app.models.users import Users


class CreditLines(Base):
    __tablename__ = "credit_lines"
    __table_args__ = (
        Index(
            "ux_credit_lines_legacy_credit_line_id",
            "legacy_credit_line_id",
            unique=True,
            postgresql_where=text("legacy_credit_line_id IS NOT NULL"),
        ),
        {"schema": "paylink"},
    )

    credit_line_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    currency_code = Column(CHAR(3), nullable=False)
    initial_amount = Column(Numeric(12, 2), nullable=False)
    used_amount = Column(Numeric(12, 2), nullable=False, server_default=text("0"))
    outstanding_amount = Column(Numeric(12, 2), nullable=False, server_default=text("0"))
    status = Column(Text, nullable=False)
    source = Column(Text)
    legacy_sendlog_id = Column(Numeric(19, 0))
    legacy_credit_line_id = Column(Numeric(19, 0))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime(timezone=True))

    user = relationship("Users", back_populates="credit_lines")
    events = relationship("CreditLineEvents", back_populates="credit_line")
    payments = relationship("CreditLinePayments", back_populates="credit_line")
