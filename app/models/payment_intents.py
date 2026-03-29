import enum

from sqlalchemy import CHAR, Column, DateTime, Enum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PaymentIntentDirection(str, enum.Enum):
    DEPOSIT = "deposit"


class PaymentIntentRail(str, enum.Enum):
    MOBILE_MONEY = "mobile_money"
    BANK_TRANSFER = "bank_transfer"


class PaymentIntentStatus(str, enum.Enum):
    CREATED = "created"
    PENDING_PROVIDER = "pending_provider"
    SETTLED = "settled"
    CREDITED = "credited"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentIntents(Base):
    __tablename__ = "payment_intents"
    __table_args__ = {"schema": "paylink"}

    intent_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="CASCADE"), nullable=False)
    direction = Column(
        Enum(
            PaymentIntentDirection,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="payment_intent_direction",
            schema="paylink",
            validate_strings=True,
        ),
        nullable=False,
    )
    rail = Column(
        Enum(
            PaymentIntentRail,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="payment_intent_rail",
            schema="paylink",
            validate_strings=True,
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            PaymentIntentStatus,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="payment_intent_status",
            schema="paylink",
            validate_strings=True,
        ),
        nullable=False,
        server_default=PaymentIntentStatus.CREATED.value,
    )
    provider_code = Column(Text, nullable=False)
    provider_channel = Column(Text)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    merchant_reference = Column(Text, nullable=False, unique=True)
    provider_reference = Column(Text)
    payer_identifier = Column(Text)
    credited_tx_id = Column(UUID(as_uuid=True))
    target_instructions = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    settled_at = Column(DateTime(timezone=True))
    credited_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=text("now()"),
    )
