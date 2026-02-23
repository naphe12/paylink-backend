from sqlalchemy import Column, Text, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.core.database import Base

class AMLCase(Base):
    __tablename__ = "cases"
    __table_args__ = ({"schema": "aml"},)

    case_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="SET NULL"))

    status = Column(Text, nullable=False, server_default=text("'OPEN'"))
    risk_score = Column(Integer, nullable=False, server_default=text("0"))
    reason = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(TIMESTAMP(timezone=True))
