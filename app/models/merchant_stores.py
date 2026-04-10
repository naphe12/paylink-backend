from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantStores(Base):
    __tablename__ = "merchant_stores"
    __table_args__ = (
        UniqueConstraint("merchant_id", "code", name="merchant_stores_merchant_code_key"),
        CheckConstraint(
            "status IN ('active','paused','archived')",
            name="merchant_stores_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    store_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_profiles.merchant_id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(Text)
    name = Column(Text, nullable=False)
    country_code = Column(CHAR(2))
    city = Column(Text)
    address_line = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'active'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
