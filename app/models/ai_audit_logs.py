from sqlalchemy import Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AiAuditLogs(Base):
    __tablename__ = "ai_audit_logs"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    session_id = Column(UUID(as_uuid=True))
    raw_message = Column(Text, nullable=False)
    parsed_intent = Column(JSONB)
    resolved_command = Column(JSONB)
    action_taken = Column(Text)
    status = Column(Text, nullable=False)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
