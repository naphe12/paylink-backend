from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class UserCurrencyPreferences(Base):
    __tablename__ = "user_currency_preferences"
    __table_args__ = {"schema": "product_fx"}

    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), primary_key=True)
    display_currency = Column(String(5), nullable=False)
    auto_convert_small_balances = Column(Boolean, nullable=False, server_default=text("false"))
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
