from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, Boolean, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SupportCaseMessages(Base):
    __tablename__ = "support_case_messages"
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('comment','internal_note','status_update','system')",
            name="support_case_messages_type_valid",
        ),
        {"schema": "product_support"},
    )

    message_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_support.support_cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    author_role = Column(Text, nullable=False)
    message_type = Column(Text, nullable=False, server_default=text("'comment'"))
    body = Column(Text, nullable=False)
    is_visible_to_customer = Column(Boolean, nullable=False, server_default=text("true"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
