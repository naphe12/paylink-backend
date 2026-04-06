from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SupportCases(Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        CheckConstraint(
            "category IN ('payment_request','wallet','p2p','escrow','cash_in','cash_out','kyc','fraud','other')",
            name="support_cases_category_valid",
        ),
        CheckConstraint(
            "status IN ('open','in_review','waiting_user','resolved','closed')",
            name="support_cases_status_valid",
        ),
        CheckConstraint(
            "priority IN ('low','normal','high','urgent')",
            name="support_cases_priority_valid",
        ),
        {"schema": "product_support"},
    )

    case_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    entity_type = Column(Text)
    entity_id = Column(Text)
    category = Column(Text, nullable=False)
    subject = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'open'"))
    priority = Column(Text, nullable=False, server_default=text("'normal'"))
    reason_code = Column(Text)
    resolution_code = Column(Text)
    sla_due_at = Column(DateTime(timezone=True))
    first_response_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
