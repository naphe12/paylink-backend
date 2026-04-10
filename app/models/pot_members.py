from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PotMembers(Base):
    __tablename__ = "pot_members"
    __table_args__ = {"schema": "product_pots"}

    membership_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    pot_id = Column(UUID(as_uuid=True), ForeignKey("product_pots.pots.pot_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False, server_default=text("'member'"))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    target_amount = Column(Numeric(20, 6))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
