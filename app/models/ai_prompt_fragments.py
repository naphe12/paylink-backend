from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AiPromptFragments(Base):
    __tablename__ = "ai_prompt_fragments"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intent_code = Column(Text, ForeignKey("ia.ai_intents.intent_code", ondelete="CASCADE"), nullable=False)
    fragment_type = Column(Text, nullable=False, server_default=text("'feedback_hint'"))
    content = Column(Text, nullable=False)
    language_code = Column(Text, nullable=False, server_default=text("'fr'"))
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
