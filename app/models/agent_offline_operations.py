from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AgentOfflineOperations(Base):
    __tablename__ = "agent_offline_operations"
    __table_args__ = {"schema": "product_agent_ops"}

    operation_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("paylink.agents.agent_id", ondelete="CASCADE"), nullable=False)
    client_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    client_label = Column(Text, nullable=False)
    operation_type = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency_code = Column(Text, nullable=False)
    note = Column(Text)
    offline_reference = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, server_default=text("'queued'"))
    failure_reason = Column(Text)
    synced_response = Column(JSONB)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    queued_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
