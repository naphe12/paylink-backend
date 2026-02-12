import uuid
import decimal
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Numeric, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from models.escrow_enums import (
    EscrowOrderStatus,
    EscrowNetwork,
    EscrowPayoutMethod,
    EscrowConversionMode,
)

class EscrowOrder(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "escrow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trader_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    status: Mapped[EscrowOrderStatus] = mapped_column(
        PGEnum(
            EscrowOrderStatus,
            name="escrow_order_status",
            schema="escrow",
            create_type=False,
        ),
        default=EscrowOrderStatus.CREATED,
    )
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    usdc_expected: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    usdc_received: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8), default=0)
    usdc_fee: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8), default=0)

    conversion_mode: Mapped[EscrowConversionMode] = mapped_column(
        PGEnum(
            EscrowConversionMode,
            name="escrow_conversion_mode",
            schema="escrow",
            create_type=False,
        ),
        default=EscrowConversionMode.INVENTORY_INTERNAL,
    )
    usdt_target: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    usdt_received: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8), default=0)
    conversion_fee_usdt: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8), default=0)
    conversion_rate_usdc_usdt: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 12))

    rate_bif_usdt: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    bif_target: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 2))
    bif_paid: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 2), default=0)

    deposit_network: Mapped[EscrowNetwork] = mapped_column(
        PGEnum(
            EscrowNetwork,
            name="escrow_network",
            schema="escrow",
            create_type=False,
        )
    )
    deposit_address: Mapped[str] = mapped_column(String)
    deposit_memo: Mapped[str | None] = mapped_column(String)
    deposit_required_confirmations: Mapped[int] = mapped_column(Integer, default=1)

    deposit_tx_hash: Mapped[str | None] = mapped_column(String)
    deposit_tx_from: Mapped[str | None] = mapped_column(String)
    deposit_tx_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(24, 8))
    deposit_confirmations: Mapped[int] = mapped_column(Integer, default=0)
    funded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    swapped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    swap_reference: Mapped[str | None] = mapped_column(String)

    payout_method: Mapped[EscrowPayoutMethod] = mapped_column(
        PGEnum(
            EscrowPayoutMethod,
            name="escrow_payout_method",
            schema="escrow",
            create_type=False,
        ),
        default=EscrowPayoutMethod.MOBILE_MONEY,
    )
    payout_account_name: Mapped[str | None] = mapped_column(String)
    payout_account_number: Mapped[str | None] = mapped_column(String)
    payout_provider: Mapped[str | None] = mapped_column(String)
    payout_reference: Mapped[str | None] = mapped_column(String)
    payout_initiated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paid_out_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
