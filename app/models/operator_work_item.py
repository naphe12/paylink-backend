from sqlalchemy import Column, DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OperatorWorkItem(Base):
    __tablename__ = "operator_work_items"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_operator_work_items_entity"),
        {"schema": "paylink"},
    )

    work_item_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    entity_type = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    operator_status = Column(Text, nullable=False, server_default=text("'needs_follow_up'"))
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    blocked_reason = Column(Text)
    notes = Column(Text)
    follow_up_at = Column(DateTime(timezone=True))
    last_action_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
