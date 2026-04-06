from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class VirtualCardTransactions(Base):
    __tablename__ = "virtual_card_transactions"
    __table_args__ = {"schema": "product_cards"}

    card_tx_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    card_id = Column(UUID(as_uuid=True), ForeignKey("product_cards.virtual_cards.card_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    merchant_name = Column(Text, nullable=False)
    merchant_category = Column(Text)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    decline_reason = Column(Text)
    reference = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
