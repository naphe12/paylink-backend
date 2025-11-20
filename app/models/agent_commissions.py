# app/models/agent_commissions.py
from sqlalchemy import Column, Numeric, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class AgentCommissions(Base):
    __tablename__ = "agent_commissions"
    __table_args__ = {"schema": "paylink"}

    commission_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=False)
    operation_type = Column(Text, nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    related_tx = Column(UUID(as_uuid=True), ForeignKey("paylink.transactions.tx_id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    agent = relationship("Users", back_populates="agent_commissions")
