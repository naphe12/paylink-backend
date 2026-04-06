from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class BusinessAccounts(Base):
    __tablename__ = "business_accounts"
    __table_args__ = {"schema": "product_business"}

    business_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    legal_name = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    country_code = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
