from sqlalchemy import Column, Text, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text

from app.core.database import Base

class AMLHit(Base):
    __tablename__ = "hits"
    __table_args__ = ({"schema": "aml"},)

    hit_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="SET NULL"))
    order_id = Column(UUID(as_uuid=True), ForeignKey("escrow.orders.id", ondelete="SET NULL"))

    rule_code = Column(Text, nullable=False)
    score_delta = Column(Integer, nullable=False)
    details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
