from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowProofType, EscrowActorType

class EscrowProof(Base):
    __tablename__ = "proofs"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    proof_type: Mapped[EscrowProofType]
    proof_ref: Mapped[str] = mapped_column(String, nullable=False)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by_type: Mapped[EscrowActorType] = mapped_column(default=EscrowActorType.OPERATOR)
    created_by_id: Mapped[str | None]
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
