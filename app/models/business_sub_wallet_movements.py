from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class BusinessSubWalletMovements(Base):
    __tablename__ = "business_sub_wallet_movements"
    __table_args__ = {"schema": "product_business"}

    movement_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    sub_wallet_id = Column(UUID(as_uuid=True), ForeignKey("product_business.business_sub_wallets.sub_wallet_id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    direction = Column(Text, nullable=False)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    note = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
