from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PaymentRequestReminders(Base):
    __tablename__ = "payment_request_reminders"
    __table_args__ = (
        CheckConstraint(
            "reminder_type IN ('manual','auto_due','auto_overdue')",
            name="payment_request_reminders_type_valid",
        ),
        CheckConstraint(
            "status IN ('queued','sent','failed','cancelled')",
            name="payment_request_reminders_status_valid",
        ),
        {"schema": "product_payments"},
    )

    reminder_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_payments.payment_requests.request_id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'queued'"))
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
