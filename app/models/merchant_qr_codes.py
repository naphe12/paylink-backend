from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantQrCodes(Base):
    __tablename__ = "merchant_qr_codes"
    __table_args__ = (
        UniqueConstraint("token", name="merchant_qr_codes_token_key"),
        CheckConstraint("fixed_amount IS NULL OR fixed_amount > 0", name="merchant_qr_codes_amount_positive"),
        CheckConstraint(
            "qr_type IN ('static','dynamic')",
            name="merchant_qr_codes_type_valid",
        ),
        CheckConstraint(
            "status IN ('active','disabled','expired')",
            name="merchant_qr_codes_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    qr_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
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
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
    )
    qr_type = Column(Text, nullable=False)
    token = Column(Text, nullable=False)
    fixed_amount = Column(Numeric(20, 6))
    currency_code = Column(CHAR(3))
    label = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'active'"))
    template_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
