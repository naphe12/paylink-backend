from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class EscrowEvent(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
