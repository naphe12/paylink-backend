from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class FinancialBudgetRules(Base):
    __tablename__ = "financial_budget_rules"
    __table_args__ = (
        CheckConstraint("limit_amount > 0", name="financial_budget_rules_limit_positive"),
        {"schema": "product_finance"},
    )

    rule_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    category = Column(Text, nullable=False)
    limit_amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
