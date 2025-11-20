# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LoanRepayments(Base):
    __tablename__ = 'loan_repayments'
    __table_args__ = (
        ForeignKeyConstraint(['loan_id'], ['paylink.loans.loan_id'], ondelete='CASCADE', name='loan_repayments_loan_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='loan_repayments_tx_id_fkey'),
        PrimaryKeyConstraint('repayment_id', name='loan_repayments_pkey'),
        {'schema': 'paylink'}
    )

    repayment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    loan_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    paid_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6), server_default=text('0'))
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    loan: Mapped['Loans'] = relationship('Loans', back_populates='loan_repayments')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='loan_repayments')
from app.models.loans import Loans
from app.models.transactions import Transactions
