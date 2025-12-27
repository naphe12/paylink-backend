# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Loans(Base):
    __tablename__ = 'loans'
    __table_args__ = (
        ForeignKeyConstraint(['borrower_user'], ['paylink.users.user_id'], ondelete='CASCADE', name='loans_borrower_user_fkey'),
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='loans_currency_code_fkey'),
        PrimaryKeyConstraint('loan_id', name='loans_pkey'),
        {'schema': 'paylink'}
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    borrower_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    principal: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    apr_percent: Mapped[decimal.Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Enum('draft', 'active', 'in_arrears', 'repaid', 'written_off', name='loan_status', schema='paylink'), nullable=False, server_default=text("'draft'::paylink.loan_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    risk_level: Mapped[Optional[str]] = mapped_column(Enum('low', 'medium', 'high', 'critical', name='risk_level', schema='paylink'), server_default=text("'low'::paylink.risk_level"))
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    product_type: Mapped[Optional[str]] = mapped_column(Enum('consumer', 'business', name='loan_product_type', schema='paylink'), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_activity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monthly_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    penalty_rate_percent: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(7, 4), nullable=True)
    grace_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    users: Mapped['Users'] = relationship('Users', back_populates='loans')
    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='loans')
    loan_repayments: Mapped[list['LoanRepayments']] = relationship('LoanRepayments', back_populates='loan')

from app.models.currencies import Currencies
from app.models.loanrepayments import LoanRepayments
from app.models.users import Users
