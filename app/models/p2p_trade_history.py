from sqlalchemy import Column, BigInteger, Text, ForeignKey, Enum, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.p2p_enums import TradeStatus

class P2PTradeStatusHistory(Base):
    __tablename__ = "trade_status_history"
    __table_args__ = ({"schema": "p2p"},)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="CASCADE"), nullable=False)

    from_status = Column(Enum(TradeStatus, name="trade_status", schema="p2p"))
    to_status = Column(Enum(TradeStatus, name="trade_status", schema="p2p"), nullable=False)

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    actor_role = Column(Text, nullable=False, server_default="SYSTEM")
    note = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
