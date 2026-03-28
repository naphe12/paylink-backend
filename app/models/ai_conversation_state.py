from sqlalchemy import Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AiConversationState(Base):
    __tablename__ = "ai_conversation_state"
    __table_args__ = {"schema": "ia"}

    session_id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    current_intent = Column(Text)
    collected_slots = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    state = Column(Text, nullable=False, server_default=text("'active'"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
