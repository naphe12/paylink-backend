from sqlalchemy import Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AiPendingActions(Base):
    __tablename__ = "ai_pending_actions"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True))
    intent_code = Column(Text, nullable=False)
    action_code = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'pending'"))
    result_payload = Column(JSONB)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))
