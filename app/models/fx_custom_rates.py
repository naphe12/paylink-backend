from sqlalchemy import (TIMESTAMP, Boolean, Column, Integer, Numeric, String,
                        text)

from app.core.database import Base


class FxCustomRates(Base):
    __tablename__ = "fx_custom_rates"
    __table_args__ = {"schema": "paylink"}

    rate_id = Column(Integer, primary_key=True, autoincrement=True)
    origin_currency = Column(String(3), nullable=False, default="EUR")
    destination_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(12, 2), nullable=False)
    source = Column(String(50), default="parallel_market")
    is_active = Column(Boolean, default=True)
    updated_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
