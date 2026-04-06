from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class MerchantPaymentAttempts(Base):
    __tablename__ = "merchant_payment_attempts"
    __table_args__ = (
        UniqueConstraint("payment_intent_id", name="merchant_payment_attempts_payment_intent_id_key"),
        UniqueConstraint("wallet_tx_id", name="merchant_payment_attempts_wallet_tx_id_key"),
        CheckConstraint("amount > 0", name="merchant_payment_attempts_amount_positive"),
        CheckConstraint(
            "rail IN ('wallet','mobile_money','bank_transfer','virtual_card','external')",
            name="merchant_payment_attempts_rail_valid",
        ),
        CheckConstraint(
            "status IN ('created','pending','authorized','settled','failed','cancelled','expired')",
            name="merchant_payment_attempts_status_valid",
        ),
        {"schema": "product_merchant_payments"},
    )

    attempt_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_merchant_payments.merchant_orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    payer_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    payer_wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="SET NULL"))
    rail = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default=text("'created'"))
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    payment_intent_id = Column(UUID(as_uuid=True), ForeignKey("paylink.payment_intents.intent_id", ondelete="SET NULL"))
    wallet_tx_id = Column(UUID(as_uuid=True), ForeignKey("paylink.transactions.tx_id", ondelete="SET NULL"))
    provider_reference = Column(Text)
    failure_code = Column(Text)
    failure_reason = Column(Text)
    authorized_at = Column(DateTime(timezone=True))
    settled_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
