from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class EscrowPolicy(Base):
    __tablename__ = "policies"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_key: Mapped[str] = mapped_column(String, unique=True)
    policy_value: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
