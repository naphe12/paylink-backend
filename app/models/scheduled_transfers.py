from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class ScheduledTransfers(Base):
    __tablename__ = "scheduled_transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="scheduled_transfers_amount_positive"),
        CheckConstraint(
            "frequency IN ('daily','weekly','monthly')",
            name="scheduled_transfers_frequency_valid",
        ),
        CheckConstraint(
            "status IN ('active','paused','cancelled','completed','failed')",
            name="scheduled_transfers_status_valid",
        ),
        CheckConstraint(
            "remaining_runs IS NULL OR remaining_runs >= 0",
            name="scheduled_transfers_remaining_runs_non_negative",
        ),
        {"schema": "product_transfers"},
    )

    schedule_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    receiver_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    receiver_identifier = Column(Text, nullable=False)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    frequency = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'active'"))
    note = Column(Text)
    next_run_at = Column(DateTime(timezone=True), nullable=False)
    last_run_at = Column(DateTime(timezone=True))
    last_result = Column(Text)
    remaining_runs = Column(Integer)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
