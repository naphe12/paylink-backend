from sqlalchemy import Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class BusinessMembers(Base):
    __tablename__ = "business_members"
    __table_args__ = {"schema": "product_business"}

    membership_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    business_id = Column(UUID(as_uuid=True), ForeignKey("product_business.business_accounts.business_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'active'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
