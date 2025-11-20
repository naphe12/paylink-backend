# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BillPayments(Base):
    __tablename__ = 'bill_payments'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['paylink.invoices.invoice_id'], ondelete='CASCADE', name='bill_payments_invoice_id_fkey'),
        ForeignKeyConstraint(['tx_id'], ['paylink.transactions.tx_id'], name='bill_payments_tx_id_fkey'),
        PrimaryKeyConstraint('bill_payment_id', name='bill_payments_pkey'),
        {'schema': 'paylink'}
    )

    bill_payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    paid_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='bill_payments')
    tx: Mapped[Optional['Transactions']] = relationship('Transactions', back_populates='bill_payments')
from app.models.invoices import Invoices
from app.models.transactions import Transactions
