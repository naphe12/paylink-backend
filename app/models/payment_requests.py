from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class PaymentRequests(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="payment_requests_amount_positive"),
        CheckConstraint(
            "status IN ('draft','pending','paid','declined','cancelled','expired')",
            name="payment_requests_status_valid",
        ),
        CheckConstraint(
            "payer_user_id IS NULL OR payer_user_id <> requester_user_id",
            name="payment_requests_requester_payer_diff",
        ),
        {"schema": "product_payments"},
    )

    request_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    requester_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    payer_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    requester_wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="RESTRICT"), nullable=False)
    payer_wallet_id = Column(UUID(as_uuid=True), ForeignKey("paylink.wallets.wallet_id", ondelete="SET NULL"))
    related_tx_id = Column(UUID(as_uuid=True), ForeignKey("paylink.transactions.tx_id", ondelete="SET NULL"))
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    status = Column(Text, nullable=False, server_default=text("'pending'"))
    channel = Column(Text, nullable=False, server_default=text("'direct'"))
    title = Column(Text)
    note = Column(Text)
    share_token = Column(Text, unique=True)
    due_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    paid_at = Column(DateTime(timezone=True))
    declined_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    last_reminder_at = Column(DateTime(timezone=True))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
