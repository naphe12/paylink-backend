from sqlalchemy import Column, Text, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text

from app.core.database import Base

class P2PPaymentProof(Base):
    __tablename__ = "payment_proofs"
    __table_args__ = ({"schema": "p2p"},)

    proof_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))

    kind = Column(Text, nullable=False, server_default=text("'FIAT_PROOF'"))
    url = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
