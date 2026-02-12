import decimal
from datetime import datetime

from sqlalchemy import String, Numeric
from sqlalchemy.dialects.postgresql import TIMESTAMP, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowConversionMode

class EscrowSwap(Base):
    __tablename__ = "swaps"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    mode: Mapped[EscrowConversionMode] = mapped_column(
        PGEnum(
            EscrowConversionMode,
            name="escrow_conversion_mode",
            schema="escrow",
            create_type=False,
        )
    )
    input_symbol: Mapped[str] = mapped_column(String, default="USDC")
    output_symbol: Mapped[str] = mapped_column(String, default="USDT")
    input_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    output_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    fee_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8), default=0)
    rate: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 12))
    reference: Mapped[str | None] = mapped_column(String)
    executed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
