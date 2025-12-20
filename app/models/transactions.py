# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# app/models/transactions.py
import datetime
import decimal
import uuid
from typing import Optional
from sqlalchemy import (
    Column, Numeric, CHAR, Enum, DateTime, Text, ForeignKeyConstraint,
    PrimaryKeyConstraint, CheckConstraint, Index, text
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Transactions(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0::numeric"),
        ForeignKeyConstraint(["currency_code"], ["paylink.currencies.currency_code"]),
        ForeignKeyConstraint(["initiated_by"], ["paylink.users.user_id"]),
        ForeignKeyConstraint(["receiver_wallet"], ["paylink.wallets.wallet_id"]),
        ForeignKeyConstraint(["sender_wallet"], ["paylink.wallets.wallet_id"]),
        PrimaryKeyConstraint("tx_id"),
        Index("idx_tx_receiver", "receiver_wallet"),
        Index("idx_tx_sender", "sender_wallet"),
        Index("idx_tx_status", "status"),
        {"schema": "paylink"},
    )

    tx_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(CHAR(3), nullable=False)
    channel = Column(
        Enum(
            "mobile_money",
            "bank",
            "card",
            "external_transfer",
            "EXTERNAL_TRANSFER",
            "cash",
            "internal",
            "bank_transfer",
            name="tx_channel",
            schema="paylink",
        ),
        nullable=False,
    )
    status = Column(Enum("initiated", "pending", "succeeded", "failed", "cancelled", "reversed", "chargeback","completed", name="tx_status", schema="paylink"), nullable=False, server_default=text("'initiated'::paylink.tx_status"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    initiated_by = Column(UUID(as_uuid=True))
    sender_wallet = Column(UUID(as_uuid=True))
    receiver_wallet = Column(UUID(as_uuid=True))
    related_entity_id = Column(UUID(as_uuid=True))
    description = Column(Text)

    # Currency relation (matches Currencies.transactions)
    currencies = relationship(
        "Currencies",
        foreign_keys=[currency_code],
        back_populates="transactions",
    )

    # Related entities with back_populates to this transaction
    aml_events = relationship("AmlEvents", back_populates="tx")
    bill_payments = relationship("BillPayments", back_populates="tx")
    disputes = relationship("Disputes", back_populates="tx")
    fx_conversions = relationship("FxConversions", back_populates="tx")
    loan_repayments = relationship("LoanRepayments", back_populates="tx")
    payment_instructions = relationship("PaymentInstructions", back_populates="tx")
    recon_lines = relationship("ReconLines", back_populates="transactions")
    tontine_contributions = relationship("TontineContributions", back_populates="tx")
    tontine_payouts = relationship("TontinePayouts", back_populates="tx")

    # ✅ Relation correcte Transactions <-> Users
    initiator = relationship(
        "Users",
        foreign_keys=[initiated_by],
        back_populates="transactions_initiated",
    )

    # ✅ Relations correctes Transactions <-> Wallets
    wallet_sender = relationship(
        "Wallets",
        foreign_keys=[sender_wallet],
        back_populates="payment_transactions_out",
    )

    wallet_receiver = relationship(
        "Wallets",
        foreign_keys=[receiver_wallet],
        back_populates="payment_transactions_in",
    )


    


from app.models.amlevents import AmlEvents
from app.models.billpayments import BillPayments
from app.models.currencies import Currencies
from app.models.disputes import Disputes
from app.models.fxconversions import FxConversions
from app.models.loanrepayments import LoanRepayments
from app.models.paymentinstructions import PaymentInstructions
from app.models.reconlines import ReconLines
from app.models.tontinecontributions import TontineContributions
from app.models.tontinepayouts import TontinePayouts
from app.models.users import Users
from app.models.wallets import Wallets
