from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class VirtualCards(Base):
    __tablename__ = "virtual_cards"
    __table_args__ = {"schema": "product_cards"}

    card_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    linked_wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="SET NULL"))
    cardholder_name = Column(Text, nullable=False)
    brand = Column(Text, nullable=False, server_default=text("'visa'"))
    card_type = Column(Text, nullable=False, server_default=text("'standard'"))
    currency_code = Column(Text, nullable=False)
    masked_pan = Column(Text, nullable=False)
    last4 = Column(Text, nullable=False)
    exp_month = Column(Integer, nullable=False)
    exp_year = Column(Integer, nullable=False)
    spending_limit = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    spent_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    frozen_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
