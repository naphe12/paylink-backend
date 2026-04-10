from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SavingsGoals(Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="savings_goals_target_positive"),
        CheckConstraint("current_amount >= 0", name="savings_goals_current_non_negative"),
        CheckConstraint(
            "status IN ('active','completed','cancelled')",
            name="savings_goals_status_valid",
        ),
        {"schema": "product_savings"},
    )

    goal_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    note = Column(Text)
    currency_code = Column(Text, nullable=False)
    target_amount = Column(Numeric(20, 6), nullable=False)
    current_amount = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    locked = Column(Boolean, nullable=False, server_default=text("false"))
    target_date = Column(DateTime(timezone=True))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
