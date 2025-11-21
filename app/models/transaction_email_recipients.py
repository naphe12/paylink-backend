import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TransactionEmailRecipient(Base):
    __tablename__ = "transaction_email_recipients"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_tx_email_recipient_user"),
        UniqueConstraint("email", name="uq_tx_email_recipient_email"),
        {"schema": "paylink"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default="now()", nullable=False
    )
