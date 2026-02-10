import uuid
from sqlalchemy import String, Integer, Numeric, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
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

    status: Mapped[EscrowOrderStatus] = mapped_column(default=EscrowOrderStatus.CREATED)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    expires_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped = mapped_column(TIMESTAMP(timezone=True))

    usdc_expected: Mapped = mapped_column(Numeric(24, 8))
    usdc_received: Mapped = mapped_column(Numeric(24, 8), default=0)
    usdc_fee: Mapped = mapped_column(Numeric(24, 8), default=0)

    conversion_mode: Mapped[EscrowConversionMode] = mapped_column(default=EscrowConversionMode.INVENTORY_INTERNAL)
    usdt_target: Mapped = mapped_column(Numeric(24, 8))
    usdt_received: Mapped = mapped_column(Numeric(24, 8), default=0)
    conversion_fee_usdt: Mapped = mapped_column(Numeric(24, 8), default=0)
    conversion_rate_usdc_usdt: Mapped = mapped_column(Numeric(24, 12))

    rate_bif_usdt: Mapped = mapped_column(Numeric(24, 8))
    bif_target: Mapped = mapped_column(Numeric(24, 2))
    bif_paid: Mapped = mapped_column(Numeric(24, 2), default=0)

    deposit_network: Mapped[EscrowNetwork]
    deposit_address: Mapped[str] = mapped_column(String)
    deposit_memo: Mapped[str | None] = mapped_column(String)
    deposit_required_confirmations: Mapped[int] = mapped_column(Integer, default=1)

    deposit_tx_hash: Mapped[str | None] = mapped_column(String)
    deposit_tx_from: Mapped[str | None] = mapped_column(String)
    deposit_tx_amount: Mapped = mapped_column(Numeric(24, 8))
    deposit_confirmations: Mapped[int] = mapped_column(Integer, default=0)
    funded_at: Mapped = mapped_column(TIMESTAMP(timezone=True))

    swapped_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    swap_reference: Mapped[str | None] = mapped_column(String)

    payout_method: Mapped[EscrowPayoutMethod] = mapped_column(default=EscrowPayoutMethod.MOBILE_MONEY)
    payout_account_name: Mapped[str | None] = mapped_column(String)
    payout_account_number: Mapped[str | None] = mapped_column(String)
    payout_provider: Mapped[str | None] = mapped_column(String)
    payout_reference: Mapped[str | None] = mapped_column(String)
    payout_initiated_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    paid_out_at: Mapped = mapped_column(TIMESTAMP(timezone=True))

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    created_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped = mapped_column(TIMESTAMP(timezone=True))
