# Auto-generated from database schema
import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AgentLocations(Base):
    __tablename__ = 'agent_locations'
    __table_args__ = (
        ForeignKeyConstraint(['agent_id'], ['paylink.agents.agent_id'], ondelete='CASCADE', name='agent_locations_agent_id_fkey'),
        PrimaryKeyConstraint('location_id', name='agent_locations_pkey'),
        {'schema': 'paylink'}
    )

    location_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    label: Mapped[Optional[str]] = mapped_column(Text)
    lat: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    lng: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    address: Mapped[Optional[str]] = mapped_column(Text)

    agent: Mapped['Agents'] = relationship('Agents', back_populates='agent_locations')

from app.models.agents import Agents
