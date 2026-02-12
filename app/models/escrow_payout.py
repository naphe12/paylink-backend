import decimal
from datetime import datetime

from sqlalchemy import String, Numeric
from sqlalchemy.dialects.postgresql import TIMESTAMP, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import EscrowPayoutMethod

class EscrowPayout(Base):
    __tablename__ = "payouts"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str]
    method: Mapped[EscrowPayoutMethod] = mapped_column(
        PGEnum(
            EscrowPayoutMethod,
            name="escrow_payout_method",
            schema="escrow",
            create_type=False,
        )
    )
    provider: Mapped[str | None] = mapped_column(String)
    account_name: Mapped[str | None] = mapped_column(String)
    account_number: Mapped[str | None] = mapped_column(String)
    amount_bif: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 2))
    reference: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    initiated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String)
