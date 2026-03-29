from sqlalchemy import Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PaymentEvents(Base):
    __tablename__ = "payment_events"
    __table_args__ = {"schema": "paylink"}

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intent_id = Column(UUID(as_uuid=True), ForeignKey("paylink.payment_intents.intent_id", ondelete="CASCADE"), nullable=False)
    provider_code = Column(Text, nullable=False)
    provider_event_type = Column(Text)
    external_event_id = Column(Text)
    provider_reference = Column(Text)
    status = Column(Text)
    reason_code = Column(Text)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
