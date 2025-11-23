# Auto-generated style model for agent_accounts
import datetime
import uuid

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class AgentAccounts(Base):
    __tablename__ = "agent_accounts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id"],
            ["paylink.agents.agent_id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="fk_agent_accounts",
        ),
        PrimaryKeyConstraint("id", name="agent_accounts_pkey"),
        {"schema": "paylink"},
    )

    id = Column(
        Integer,
        primary_key=True,
        server_default=text("nextval('paylink.agent_accounts_id_seq'::regclass)"),
    )
    agent_id = Column(UUID(as_uuid=True), nullable=False)
    service = Column(String(50), nullable=False)
    account_service = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    agent = relationship("Agents", back_populates="agent_accounts")

