from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class TontineInvitations(Base):
    __tablename__ = "tontine_invitations"
    __table_args__ = {"schema": "paylink"}

    invitation_id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    tontine_id = Column(UUID(as_uuid=True), ForeignKey("paylink.tontines.tontine_id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    invite_code = Column(String(12), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id"), nullable=True)
