from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ClientBalanceEvents(Base):
    __tablename__ = "client_balance_events"
    __table_args__ = {"schema": "paylink"}

    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    balance_before = Column(Numeric(20, 2))
    balance_after = Column(Numeric(20, 2))
    amount_delta = Column(Numeric(20, 2))
    source = Column(Text, server_default=text("'legacy'"))
    legacy_id = Column(Numeric(19, 0))
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    currency = Column(CHAR(3), nullable=False)
    user = relationship("Users", back_populates="client_balance_events")
