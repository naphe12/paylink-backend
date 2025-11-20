# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Numeric, ForeignKeyConstraint, PrimaryKeyConstraint,
    UniqueConstraint, Index, Enum, CHAR, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# app/models/wallets.py
import uuid
from sqlalchemy import Column, Enum, Numeric, CHAR, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Wallets(Base):
    __tablename__ = "wallets"
    __table_args__ = {"schema": "paylink"}

    wallet_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    type = Column(Enum("consumer", "agent", "merchant", "settlement", "reserve",'admin' , name="wallet_type", schema="paylink"), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)

    available = Column(Numeric(20, 6), server_default=text("0"), nullable=False)
    pending = Column(Numeric(20, 6), server_default=text("0"), nullable=False)
    bonus_balance = Column(Numeric(12, 2), server_default=text("0"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))

    # ✅ Relation User
    user = relationship("Users", back_populates="wallets")

    # Currency relation (matches Currencies.wallets)
    currencies = relationship(
        "Currencies",
        back_populates="wallets",
        primaryjoin="foreign(Wallets.currency_code) == Currencies.currency_code",
    )

    # ✅ Relations Transactions <-> Wallets (cohérentes)
    payment_transactions_out = relationship(
        "Transactions",
        foreign_keys="Transactions.sender_wallet",
        back_populates="wallet_sender",
    )

    payment_transactions_in = relationship(
        "Transactions",
        foreign_keys="Transactions.receiver_wallet",
        back_populates="wallet_receiver",
    )

    # WalletTransactions reverse relation
    transactions = relationship("WalletTransactions", back_populates="wallet")

    # Merchant reverse relation (matches Merchants.wallet)
    merchants = relationship("Merchants", back_populates="wallet")




from app.models.currencies import Currencies
from app.models.merchants import Merchants
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
