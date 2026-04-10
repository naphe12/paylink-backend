from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class ReferralRewards(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = {"schema": "product_growth"}

    reward_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    referrer_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    referred_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, server_default=text("'pending'"))
    activation_reason = Column(Text)
    amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    currency_code = Column(Text, nullable=False, server_default=text("'BIF'"))
    credited = Column(Boolean, nullable=False, server_default=text("false"))
    activated_at = Column(DateTime(timezone=True))
    credited_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
