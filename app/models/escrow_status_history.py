import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowOrderStatus, EscrowActorType

class EscrowStatusHistory(Base):
    __tablename__ = "status_history"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    old_status: Mapped[EscrowOrderStatus | None] = mapped_column(
        PGEnum(
            EscrowOrderStatus,
            name="escrow_order_status",
            schema="escrow",
            create_type=False,
        )
    )
    new_status: Mapped[EscrowOrderStatus] = mapped_column(
        PGEnum(
            EscrowOrderStatus,
            name="escrow_order_status",
            schema="escrow",
            create_type=False,
        )
    )
    actor_type: Mapped[EscrowActorType] = mapped_column(
        PGEnum(
            EscrowActorType,
            name="escrow_actor_type",
            schema="escrow",
            create_type=False,
        ),
        default=EscrowActorType.SYSTEM,
    )
    actor_id: Mapped[uuid.UUID | None]
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
