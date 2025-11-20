from sqlalchemy import Column, Text, Numeric, TIMESTAMP, ForeignKey, Enum, CHAR
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.core.database import Base

class WalletEntryDirectionEnum(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    credit='credit'
    debit = 'debit'
 



class WalletTransactions(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = ({"schema": "paylink"},)

    transaction_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    wallet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.wallets.wallet_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="SET NULL"),
    )

    operation_type = Column(Text, nullable=False)
    direction = Column(
        Enum("credit", "debit","DEBIT","CREDIT", name="wallet_entry_direction", schema="paylink"),
        nullable=False,
    )
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False)
    reference = Column(Text)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    wallet = relationship("Wallets", back_populates="transactions")
    user = relationship("Users", back_populates="wallet_transactions")
