from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantRefunds(Base):
    __tablename__ = "merchant_refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="merchant_refunds_amount_positive"),
        CheckConstraint(
            "status IN ('created','pending','completed','failed','cancelled')",
            name="merchant_refunds_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    refund_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_profiles.merchant_id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_payment_attempts.attempt_id", ondelete="SET NULL"),
    )
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    reason = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'created'"))
    refund_tx_id = Column(UUID(as_uuid=True), ForeignKey("paylink.transactions.tx_id", ondelete="SET NULL"))
    provider_reference = Column(Text)
    completed_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
