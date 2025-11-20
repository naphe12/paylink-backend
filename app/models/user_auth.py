# app/models/user_auth.py
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserAuth(Base):
    __tablename__ = "user_auth"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["paylink.users.user_id"],
            name="user_auth_user_id_fkey",
            ondelete="CASCADE",
        ),
        {"schema": "paylink"},
    )

    # --- Colonnes ---
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )

    password_hash: Mapped[str] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relations ---
    user: Mapped["Users"] = relationship("Users", back_populates="auth")

from app.models.users import Users
