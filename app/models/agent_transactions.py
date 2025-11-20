from sqlalchemy import Column, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTransactions(Base):
    __tablename__ = "agent_transactions"
    __table_args__ = {"schema": "paylink"}

    transaction_id = Column(
        "id", Integer, primary_key=True, autoincrement=True
    )
    related_tx= Column(
        "related_tx", UUID(as_uuid=True),  nullable=False)
    agent_user_id = Column(
        UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=False
    )
    client_user_id = Column(
        "user_id", UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=False
    )
    direction = Column(Text, nullable=False)
    tx_type = Column("type", Text)
    amount = Column(Numeric(14, 2), nullable=False)
    commission = Column(Numeric(12, 2), nullable=False, server_default="0")
    status = Column(Text, nullable=False, server_default="completed")
    created_at = Column(
        "processed_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    agent = relationship("Users", foreign_keys=[agent_user_id])
    client = relationship("Users", foreign_keys=[client_user_id])
