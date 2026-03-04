from sqlalchemy import BigInteger, Column, ForeignKey, Numeric, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func, text

from app.core.database import Base


class P2PChainDeposit(Base):
    __tablename__ = "chain_deposits"
    __table_args__ = ({"schema": "p2p"},)

    deposit_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    trade_id = Column(UUID(as_uuid=True), ForeignKey("p2p.trades.trade_id", ondelete="SET NULL"))

    tx_hash = Column(Text, nullable=False)
    log_index = Column(BigInteger, nullable=False, server_default=text("0"))
    network = Column(Text, nullable=False)
    token = Column(Text, nullable=False)
    to_address = Column(Text, nullable=False)
    amount = Column(Numeric(24, 8), nullable=False)

    block_number = Column(BigInteger)
    block_timestamp = Column(TIMESTAMP(timezone=True))

    status = Column(Text, nullable=False)
    resolution = Column(Text)
    matched_at = Column(TIMESTAMP(timezone=True))
    matched_by = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))

    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
