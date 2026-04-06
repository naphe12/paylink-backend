from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PotContributions(Base):
    __tablename__ = "pot_contributions"
    __table_args__ = {"schema": "product_pots"}

    contribution_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    pot_id = Column(UUID(as_uuid=True), ForeignKey("product_pots.pots.pot_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    note = Column(Text)
    source = Column(Text, nullable=False, server_default=text("'wallet'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
