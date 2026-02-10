import uuid
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowOrderStatus, EscrowActorType

class EscrowStatusHistory(Base):
    __tablename__ = "status_history"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    old_status: Mapped[EscrowOrderStatus | None]
    new_status: Mapped[EscrowOrderStatus]
    actor_type: Mapped[EscrowActorType] = mapped_column(default=EscrowActorType.SYSTEM)
    actor_id: Mapped[uuid.UUID | None]
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
