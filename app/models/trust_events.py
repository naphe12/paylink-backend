from sqlalchemy import Column, DateTime, Integer, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class TrustEvents(Base):
    __tablename__ = "trust_events"
    __table_args__ = ({"schema": "product_trust"},)

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Text, nullable=False)
    source_id = Column(Text)
    score_delta = Column(Integer, nullable=False)
    reason_code = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
