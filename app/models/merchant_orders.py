from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantOrders(Base):
    __tablename__ = "merchant_orders"
    __table_args__ = (
        UniqueConstraint("merchant_id", "merchant_reference", name="merchant_orders_merchant_reference_key"),
        CheckConstraint("amount > 0", name="merchant_orders_amount_positive"),
        CheckConstraint("collected_amount >= 0", name="merchant_orders_collected_non_negative"),
        CheckConstraint("refunded_amount >= 0", name="merchant_orders_refunded_non_negative"),
        CheckConstraint(
            "status IN ('created','pending','paid','partially_refunded','refunded','expired','cancelled','failed')",
            name="merchant_orders_status_valid",
        ),
        CheckConstraint(
            "channel IN ('static_qr','dynamic_qr','payment_link','api','manual')",
            name="merchant_orders_channel_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    order_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_profiles.merchant_id", ondelete="CASCADE"),
        nullable=False,
    )
    store_id = Column(UUID(as_uuid=True), ForeignKey("product_merchant_payments.merchant_stores.store_id", ondelete="SET NULL"))
    terminal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_terminals.terminal_id", ondelete="SET NULL"),
    )
    channel = Column(Text, nullable=False, server_default=text("'manual'"))
    merchant_reference = Column(Text, nullable=False)
    external_reference = Column(Text)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    collected_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    refunded_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    customer_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    customer_label = Column(Text)
    description = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'created'"))
    due_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    paid_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
