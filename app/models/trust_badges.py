from sqlalchemy import Column, DateTime, Boolean, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class TrustBadges(Base):
    __tablename__ = "trust_badges"
    __table_args__ = ({"schema": "product_trust"},)

    badge_code = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
