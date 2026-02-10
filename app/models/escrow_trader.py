import uuid
from sqlalchemy import Boolean, String, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class EscrowTrader(Base):
    __tablename__ = "traders"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str | None] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    payment_channels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
