from sqlalchemy import Column, Text, ForeignKey, Enum, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.core.database import Base
from app.models.p2p_enums import DisputeStatus

class P2PDispute(Base):
    __tablename__ = "disputes"
    __table_args__ = ({"schema": "p2p"},)

    dispute_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="CASCADE"), nullable=False)

    opened_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="RESTRICT"), nullable=False)
    status = Column(Enum(DisputeStatus, name="dispute_status", schema="p2p"), nullable=False, server_default=text("'OPEN'"))

    reason = Column(Text, nullable=False)
    resolution = Column(Text)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(TIMESTAMP(timezone=True))
