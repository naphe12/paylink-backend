from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AiFeedbackAnnotations(Base):
    __tablename__ = "ai_feedback_annotations"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    audit_log_id = Column(UUID(as_uuid=True), ForeignKey("ia.ai_audit_logs.id", ondelete="CASCADE"), nullable=False)
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    status = Column(Text, nullable=False, server_default=text("'reviewed'"))
    expected_intent = Column(Text)
    expected_entities_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    parser_was_correct = Column(Boolean)
    resolver_was_correct = Column(Boolean)
    final_resolution_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
