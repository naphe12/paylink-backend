from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantWebhookEvents(Base):
    __tablename__ = "merchant_webhook_events"
    __table_args__ = {"schema": "product_merchant_api"}

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    webhook_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_api.merchant_webhooks.webhook_id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_business.business_accounts.business_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(Text, nullable=False)
    delivery_status = Column(Text, nullable=False, server_default=text("'simulated'"))
    response_status_code = Column(Integer)
    request_signature = Column(Text)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    response_body = Column(Text)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"))
    last_attempted_at = Column(DateTime(timezone=True))
    next_retry_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
