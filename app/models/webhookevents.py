# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WebhookEvents(Base):
    __tablename__ = 'webhook_events'
    __table_args__ = (
        ForeignKeyConstraint(['webhook_id'], ['paylink.webhooks.webhook_id'], ondelete='CASCADE', name='webhook_events_webhook_id_fkey'),
        PrimaryKeyConstraint('event_id', name='webhook_events_pkey'),
        {'schema': 'paylink'}
    )

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    status: Mapped[str] = mapped_column(Enum('queued', 'delivered', 'failed', 'disabled', name='webhook_status', schema='paylink'), nullable=False, server_default=text("'queued'::paylink.webhook_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    last_attempt_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    webhook: Mapped['Webhooks'] = relationship('Webhooks', back_populates='webhook_events')

from app.models.webhooks import Webhooks
