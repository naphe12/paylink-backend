# app/models/limitusage.py

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Date, Numeric, TIMESTAMP, text, ForeignKey
from app.core.database import Base
import datetime

class LimitUsage(Base):
    __tablename__ = "limit_usage"
    __table_args__ = {"schema": "paylink"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ✅ Lien direct vers Limits
    limit_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paylink.limits.limit_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        index=True
    )

    day: Mapped[datetime.date] = mapped_column(
        Date, server_default=text("CURRENT_DATE"), index=True
    )
    
    month: Mapped[datetime.date] = mapped_column(
        Date, server_default=text("date_trunc('month', now())::date"), index=True
    )

    used_daily: Mapped[Numeric] = mapped_column(Numeric, server_default=text("0"))
    used_monthly: Mapped[Numeric] = mapped_column(Numeric, server_default=text("0"))

    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        server_onupdate=text("now()")
    )

    # ✅ Relations
    limit: Mapped['Limits'] = relationship("Limits", back_populates="limit_usage")
    user: Mapped['Users'] = relationship("Users", back_populates="limit_usage")

from app.models.limits import Limits
from app.models.users import Users
