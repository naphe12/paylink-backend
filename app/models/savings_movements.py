from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SavingsMovements(Base):
    __tablename__ = "savings_movements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="savings_movements_amount_positive"),
        CheckConstraint(
            "direction IN ('in','out')",
            name="savings_movements_direction_valid",
        ),
        {"schema": "product_savings"},
    )

    movement_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    goal_id = Column(UUID(as_uuid=True), ForeignKey("product_savings.savings_goals.goal_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(20, 6), nullable=False)
    currency_code = Column(Text, nullable=False)
    direction = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    note = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
