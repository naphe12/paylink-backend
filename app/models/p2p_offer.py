from sqlalchemy import (
    Column, Text, Boolean, Integer, ForeignKey, Enum, Numeric, TIMESTAMP
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text

from app.core.database import Base
from app.models.p2p_enums import OfferSide, PaymentMethod, TokenCode

class P2POffer(Base):
    __tablename__ = "offers"
    __table_args__ = ({"schema": "p2p"},)

    offer_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    side = Column(Enum(OfferSide, name="offer_side", schema="p2p"), nullable=False)
    token = Column(Enum(TokenCode, name="token_code", schema="p2p"), nullable=False)

    price_bif_per_usd = Column(Numeric(24, 6), nullable=False)
    min_token_amount = Column(Numeric(24, 8), nullable=False)
    max_token_amount = Column(Numeric(24, 8), nullable=False)
    available_amount = Column(Numeric(24, 8), nullable=False)

    payment_method = Column(Enum(PaymentMethod, name="payment_method", schema="p2p"), nullable=False)
    payment_details = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    terms = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    requires_kyc = Column(Boolean, nullable=False, server_default=text("true"))
    min_user_age_days = Column(Integer, nullable=False, server_default=text("0"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
