from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AiFeedbackSuggestions(Base):
    __tablename__ = "ai_feedback_suggestions"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    annotation_id = Column(UUID(as_uuid=True), ForeignKey("ia.ai_feedback_annotations.id", ondelete="CASCADE"), nullable=False)
    suggestion_type = Column(Text, nullable=False)
    target_key = Column(Text, nullable=False)
    proposed_value = Column(JSONB, nullable=False)
    applied = Column(Boolean, nullable=False, server_default=text("false"))
    applied_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
