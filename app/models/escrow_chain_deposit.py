import decimal
from datetime import datetime

from sqlalchemy import String, Integer, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowNetwork

class EscrowChainDeposit(Base):
    __tablename__ = "chain_deposits"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    network: Mapped[EscrowNetwork]
    token_symbol: Mapped[str] = mapped_column(String, default="USDC")
    tx_hash: Mapped[str] = mapped_column(String, nullable=False)
    from_address: Mapped[str | None] = mapped_column(String)
    to_address: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    detected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
