from sqlalchemy import String, Numeric
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowConversionMode

class EscrowSwap(Base):
    __tablename__ = "swaps"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    mode: Mapped[EscrowConversionMode]
    input_symbol: Mapped[str] = mapped_column(String, default="USDC")
    output_symbol: Mapped[str] = mapped_column(String, default="USDT")
    input_amount: Mapped = mapped_column(Numeric(24, 8))
    output_amount: Mapped = mapped_column(Numeric(24, 8))
    fee_amount: Mapped = mapped_column(Numeric(24, 8), default=0)
    rate: Mapped = mapped_column(Numeric(24, 12))
    reference: Mapped[str | None] = mapped_column(String)
    executed_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
