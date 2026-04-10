from sqlalchemy import CheckConstraint, Column, DateTime, Integer, Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class TrustProfiles(Base):
    __tablename__ = "trust_profiles"
    __table_args__ = (
        CheckConstraint("trust_score BETWEEN 0 AND 100", name="trust_profiles_score_range"),
        CheckConstraint(
            "trust_level IN ('new','verified','trusted','premium_trusted','restricted')",
            name="trust_profiles_level_valid",
        ),
        CheckConstraint("successful_payment_requests >= 0", name="trust_profiles_payment_requests_non_negative"),
        CheckConstraint("successful_p2p_trades >= 0", name="trust_profiles_p2p_trades_non_negative"),
        CheckConstraint("dispute_count >= 0", name="trust_profiles_dispute_count_non_negative"),
        CheckConstraint("failed_obligation_count >= 0", name="trust_profiles_failed_obligation_count_non_negative"),
        CheckConstraint("chargeback_like_count >= 0", name="trust_profiles_chargeback_like_count_non_negative"),
        CheckConstraint("account_age_days >= 0", name="trust_profiles_account_age_days_non_negative"),
        {"schema": "product_trust"},
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), primary_key=True)
    trust_score = Column(Integer, nullable=False, server_default=text("0"))
    trust_level = Column(Text, nullable=False, server_default=text("'new'"))
    successful_payment_requests = Column(Integer, nullable=False, server_default=text("0"))
    successful_p2p_trades = Column(Integer, nullable=False, server_default=text("0"))
    dispute_count = Column(Integer, nullable=False, server_default=text("0"))
    failed_obligation_count = Column(Integer, nullable=False, server_default=text("0"))
    chargeback_like_count = Column(Integer, nullable=False, server_default=text("0"))
    kyc_verified = Column(Boolean, nullable=False, server_default=text("false"))
    account_age_days = Column(Integer, nullable=False, server_default=text("0"))
    last_computed_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
