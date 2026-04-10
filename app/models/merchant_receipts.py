from sqlalchemy import Column, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantReceipts(Base):
    __tablename__ = "merchant_receipts"
    __table_args__ = (
        UniqueConstraint("order_id", name="merchant_receipts_order_id_key"),
        UniqueConstraint("receipt_number", name="merchant_receipts_receipt_number_key"),
        {"schema": "product_merchant_payments"},
    )

    receipt_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    receipt_number = Column(Text, nullable=False)
    snapshot = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    issued_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    voided_at = Column(DateTime(timezone=True))
