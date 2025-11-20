# Auto-generated from database schema
import datetime
import uuid

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Webhooks(Base):
    __tablename__ = 'webhooks'
    __table_args__ = (
        PrimaryKeyConstraint('webhook_id', name='webhooks_pkey'),
        {'schema': 'paylink'}
    )

    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    subscriber_url: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Enum('queued', 'delivered', 'failed', 'disabled', name='webhook_status', schema='paylink'), nullable=False, server_default=text("'queued'::paylink.webhook_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    webhook_events: Mapped[list['WebhookEvents']] = relationship('WebhookEvents', back_populates='webhook')

from app.models.webhookevents import WebhookEvents
