from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class BusinessSubWallets(Base):
    __tablename__ = "business_sub_wallets"
    __table_args__ = {"schema": "product_business"}

    sub_wallet_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    business_id = Column(UUID(as_uuid=True), ForeignKey("product_business.business_accounts.business_id", ondelete="CASCADE"), nullable=False)
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    label = Column(Text, nullable=False)
    currency_code = Column(Text, nullable=False)
    current_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    spending_limit = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
