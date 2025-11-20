from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SecuritySeverityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SecurityEvents(Base):
    __tablename__ = "security_events"
    __table_args__ = {"schema": "paylink"}

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paylink.users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    severity: Mapped[SecuritySeverityEnum] = mapped_column(
        SAEnum(SecuritySeverityEnum, name="security_severity_event", schema="paylink"),
        nullable=False,
        default=SecuritySeverityEnum.LOW,
    )
    

    message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column('context', JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user: Mapped["Users"] = relationship(
        "Users",
        back_populates="security_events",
        primaryjoin="SecurityEvents.user_id == Users.user_id",
    )


from app.models.users import Users
