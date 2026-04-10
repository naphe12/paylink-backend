from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class ReferralProfiles(Base):
    __tablename__ = "referral_profiles"
    __table_args__ = {"schema": "product_growth"}

    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), primary_key=True)
    referral_code = Column(Text, nullable=False, unique=True)
    total_referrals = Column(Integer, nullable=False, server_default=text("0"))
    activated_referrals = Column(Integer, nullable=False, server_default=text("0"))
    rewards_earned = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    currency_code = Column(Text, nullable=False, server_default=text("'BIF'"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
