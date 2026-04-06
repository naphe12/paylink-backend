from sqlalchemy import Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantPaymentEvents(Base):
    __tablename__ = "merchant_payment_events"
    __table_args__ = {"schema": "product_merchant_payments"}

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_profiles.merchant_id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
    )
    attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_payment_attempts.attempt_id", ondelete="SET NULL"),
    )
    refund_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_refunds.refund_id", ondelete="SET NULL"),
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    event_type = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
