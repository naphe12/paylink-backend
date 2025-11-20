# Auto-generated from database schema
import datetime
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Countries(Base):
    __tablename__ = 'countries'
    __table_args__ = (
        PrimaryKeyConstraint('country_code', name='countries_pkey'),
        {'schema': 'paylink'}
    )

    country_code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    phone_prefix: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[list['Users']] = relationship('Users', back_populates='countries')
    agents: Mapped[list['Agents']] = relationship('Agents', back_populates='countries')

from app.models.agents import Agents
from app.models.users import Users
