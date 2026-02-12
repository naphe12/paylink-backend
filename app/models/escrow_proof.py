from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowProofType, EscrowActorType

class EscrowProof(Base):
    __tablename__ = "proofs"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    proof_type: Mapped[EscrowProofType] = mapped_column(
        PGEnum(
            EscrowProofType,
            name="escrow_proof_type",
            schema="escrow",
            create_type=False,
        )
    )
    proof_ref: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_by_type: Mapped[EscrowActorType] = mapped_column(
        PGEnum(
            EscrowActorType,
            name="escrow_actor_type",
            schema="escrow",
            create_type=False,
        ),
        default=EscrowActorType.OPERATOR,
    )
    created_by_id: Mapped[str | None]
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
