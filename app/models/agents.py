# Auto-generated from database schema
import datetime
import uuid
import decimal
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Agents(Base):
    __tablename__ = 'agents'
    __table_args__ = (
        ForeignKeyConstraint(['country_code'], ['paylink.countries.country_code'], name='agents_country_code_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='agents_user_id_fkey'),
        PrimaryKeyConstraint('agent_id', name='agents_pkey'),
        UniqueConstraint('user_id', name='agents_user_id_key'),
        {'schema': 'paylink'}
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    commission_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), server_default=text('0.015'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    countries: Mapped['Countries'] = relationship('Countries', back_populates='agents')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='agents')
    agent_locations: Mapped[list['AgentLocations']] = relationship('AgentLocations', back_populates='agent')
    agent_transactions = relationship(
        "AgentTransactions",
        primaryjoin=lambda: Agents.user_id == AgentTransactions.agent_user_id,
        foreign_keys=lambda: [AgentTransactions.agent_user_id],
        viewonly=True
    )
    agent_accounts: Mapped[list['AgentAccounts']] = relationship('AgentAccounts', back_populates='agent')



from app.models.agentlocations import AgentLocations
from app.models.countries import Countries
from app.models.users import Users
from app.models.agent_transactions import AgentTransactions
from app.models.agent_accounts import AgentAccounts
