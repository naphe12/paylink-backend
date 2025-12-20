import datetime
import enum

from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class WalletCashRequestType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    EXTERNAL_TRANSFER = "EXTERNAL_TRANSFER"


class WalletCashRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WalletCashRequests(Base):
    __tablename__ = "wallet_cash_requests"
    __table_args__ = {"schema": "paylink"}

    request_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    wallet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.wallets.wallet_id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(
        Enum(
            WalletCashRequestType,
            name="wallet_cash_request_type",
            schema="paylink",
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            WalletCashRequestStatus,
            name="wallet_cash_request_status",
            schema="paylink",
        ),
        nullable=False,
        server_default=WalletCashRequestStatus.PENDING.value,
    )
    amount = Column(Numeric(20, 6), nullable=False)
    fee_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    total_amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    mobile_number = Column(Text)
    provider_name = Column(Text)
    note = Column(Text)
    admin_note = Column(Text)
    metadata_ = Column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    processed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="SET NULL"),
    )
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    user = relationship("Users", foreign_keys=[user_id])
    wallet = relationship("Wallets")
    processor = relationship("Users", foreign_keys=[processed_by])
