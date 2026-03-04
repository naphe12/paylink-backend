from sqlalchemy import (
    Column, Text, Integer, ForeignKey, Enum, Numeric, TIMESTAMP
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func, text

from app.core.database import Base
from app.models.p2p_enums import TradeStatus, PaymentMethod, TokenCode

class P2PTrade(Base):
    __tablename__ = "trades"
    __table_args__ = ({"schema": "p2p"},)

    trade_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    offer_id = Column(UUID(as_uuid=True), ForeignKey("p2p.offers.offer_id", ondelete="RESTRICT"), nullable=False)

    buyer_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="RESTRICT"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="RESTRICT"), nullable=False)

    token = Column(Enum(TokenCode, name="token_code", schema="p2p"), nullable=False)
    token_amount = Column(Numeric(24, 8), nullable=False)
    price_bif_per_usd = Column(Numeric(24, 6), nullable=False)
    bif_amount = Column(Numeric(24, 2), nullable=False)

    status = Column(Enum(TradeStatus, name="trade_status", schema="p2p"), nullable=False, server_default=text("'CREATED'"))

    escrow_network = Column(Text)
    escrow_deposit_addr = Column(Text)
    escrow_deposit_ref = Column(Text)
    escrow_provider = Column(Text)
    escrow_tx_hash = Column(Text)              # unique index in DB
    escrow_lock_log_index = Column(Integer)
    escrow_locked_at = Column(TIMESTAMP(timezone=True))

    payment_method = Column(Enum(PaymentMethod, name="payment_method", schema="p2p"), nullable=False)
    fiat_sent_at = Column(TIMESTAMP(timezone=True))
    fiat_confirmed_at = Column(TIMESTAMP(timezone=True))

    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)

    risk_score = Column(Integer, nullable=False, server_default=text("0"))
    flags = Column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
