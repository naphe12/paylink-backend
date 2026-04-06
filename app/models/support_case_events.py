from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SupportCaseEvents(Base):
    __tablename__ = "support_case_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','assigned','replied','status_changed','priority_changed','resolved','closed','reopened')",
            name="support_case_events_type_valid",
        ),
        {"schema": "product_support"},
    )

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_support.support_cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    actor_role = Column(Text)
    event_type = Column(Text, nullable=False)
    before_status = Column(Text)
    after_status = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
