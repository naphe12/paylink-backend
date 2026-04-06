from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantApiKeys(Base):
    __tablename__ = "merchant_api_keys"
    __table_args__ = {"schema": "product_merchant_api"}

    key_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_business.business_accounts.business_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    key_name = Column(Text, nullable=False)
    key_prefix = Column(Text, nullable=False)
    key_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
