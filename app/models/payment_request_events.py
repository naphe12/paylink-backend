from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PaymentRequestEvents(Base):
    __tablename__ = "payment_request_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','sent','viewed','reminder_sent','paid','declined','cancelled','expired')",
            name="payment_request_events_type_valid",
        ),
        {"schema": "product_payments"},
    )

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_payments.payment_requests.request_id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    actor_role = Column(Text)
    event_type = Column(Text, nullable=False)
    before_status = Column(Text)
    after_status = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
