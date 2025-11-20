# app/models.py (extrait)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime
from app.core.database import Base
class KycVerifications(Base):
    __tablename__ = "kyc_verifications"
    __table_args__ = {"schema": "paylink"}

    kyc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(nullable=False)           # BASIC / STANDARD / ENHANCED
    status: Mapped[str] = mapped_column(nullable=False)         # pending_docs / review / approved / rejected / reupload_required
    required_docs: Mapped[list] = mapped_column(JSONB, nullable=True)
    collected_docs: Mapped[list] = mapped_column(JSONB, nullable=True)
    risk_score: Mapped[float] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
