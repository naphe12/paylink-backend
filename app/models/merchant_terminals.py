from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantTerminals(Base):
    __tablename__ = "merchant_terminals"
    __table_args__ = (
        UniqueConstraint("store_id", "label", name="merchant_terminals_store_label_key"),
        CheckConstraint(
            "channel IN ('qr','cashier','api','payment_link')",
            name="merchant_terminals_channel_valid",
        ),
        CheckConstraint(
            "status IN ('active','blocked','revoked')",
            name="merchant_terminals_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    terminal_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_stores.store_id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(Text, nullable=False)
    channel = Column(Text, nullable=False, server_default=text("'qr'"))
    device_fingerprint = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'active'"))
    last_seen_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
