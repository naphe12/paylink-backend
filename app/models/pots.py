from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class Pots(Base):
    __tablename__ = "pots"
    __table_args__ = {"schema": "product_pots"}

    pot_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    currency_code = Column(Text, nullable=False)
    target_amount = Column(Numeric(20, 6), nullable=False)
    current_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    share_token = Column(Text, unique=True)
    is_public = Column(Boolean, nullable=False, server_default=text("false"))
    deadline_at = Column(DateTime(timezone=True))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
