from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantProfiles(Base):
    __tablename__ = "merchant_profiles"
    __table_args__ = (
        UniqueConstraint("business_id", name="merchant_profiles_business_id_key"),
        CheckConstraint(
            "status IN ('draft','pending_review','active','suspended','closed')",
            name="merchant_profiles_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    merchant_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_business.business_accounts.business_id", ondelete="CASCADE"),
        nullable=False,
    )
    public_name = Column(Text, nullable=False)
    legal_name = Column(Text, nullable=False)
    country_code = Column(CHAR(2))
    settlement_wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="SET NULL"))
    default_currency = Column(CHAR(3))
    mcc = Column(Text)
    support_email = Column(Text)
    support_phone = Column(Text)
    status = Column(Text, nullable=False, server_default=text("'draft'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
