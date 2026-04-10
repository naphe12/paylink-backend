from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantPaymentLinks(Base):
    __tablename__ = "merchant_payment_links"
    __table_args__ = (
        UniqueConstraint("token", name="merchant_payment_links_token_key"),
        CheckConstraint("fixed_amount IS NULL OR fixed_amount > 0", name="merchant_payment_links_amount_positive"),
        CheckConstraint("use_count >= 0", name="merchant_payment_links_use_count_non_negative"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="merchant_payment_links_max_uses_positive"),
        CheckConstraint(
            "mode IN ('one_time','reusable')",
            name="merchant_payment_links_mode_valid",
        ),
        CheckConstraint(
            "status IN ('active','disabled','expired')",
            name="merchant_payment_links_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    link_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_profiles.merchant_id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
    )
    token = Column(Text, nullable=False)
    mode = Column(Text, nullable=False, server_default=text("'one_time'"))
    fixed_amount = Column(Numeric(20, 6))
    currency_code = Column(CHAR(3))
    max_uses = Column(Integer)
    use_count = Column(Integer, nullable=False, server_default=text("0"))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    expires_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
