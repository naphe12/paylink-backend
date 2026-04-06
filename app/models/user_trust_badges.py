from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class UserTrustBadges(Base):
    __tablename__ = "user_trust_badges"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "badge_code", name="user_trust_badges_pkey"),
        {"schema": "product_trust"},
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    badge_code = Column(Text, ForeignKey("product_trust.trust_badges.badge_code", ondelete="RESTRICT"), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
