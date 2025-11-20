# Auto-generated from database schema
import datetime
import decimal
import uuid

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tontines(Base):
    __tablename__ = 'tontines'
    __table_args__ = (
        ForeignKeyConstraint(['currency_code'], ['paylink.currencies.currency_code'], name='tontines_currency_code_fkey'),
        ForeignKeyConstraint(['owner_user'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontines_owner_user_fkey'),
        PrimaryKeyConstraint('tontine_id', name='tontines_pkey'),
        {'schema': 'paylink'}
    )

    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    owner_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    periodicity_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('30'))
    status: Mapped[str] = mapped_column(Enum('draft', 'active', 'paused', 'completed', 'cancelled', name='tontine_status', schema='paylink'), nullable=False, server_default=text("'draft'::paylink.tontine_status"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    current_round = Column(Integer, server_default="0")
    next_rotation_at = Column(DateTime(timezone=True), server_default=text("now() + interval '7 days'"))
    currencies: Mapped['Currencies'] = relationship('Currencies', back_populates='tontines')
    users: Mapped['Users'] = relationship('Users', back_populates='tontines')
    tontine_members: Mapped[list['TontineMembers']] = relationship('TontineMembers', back_populates='tontine')
    tontine_contributions: Mapped[list['TontineContributions']] = relationship('TontineContributions', back_populates='tontine')
    tontine_payouts: Mapped[list['TontinePayouts']] = relationship('TontinePayouts', back_populates='tontine')
    tontine_type: Mapped[str] = mapped_column(Enum('rotative', 'epargne', name='tontine_type', schema='paylink'), nullable=False, server_default=text("'epargne'::paylink.tontine_type"))
    common_pot: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    last_rotation_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    amount_per_member: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # app/models/tontines.py
      # ✅ On garde UNE relation officielle
    tontine_members = relationship(
        "TontineMembers",
        back_populates="tontine",
        cascade="all, delete-orphan"
    )

    # ✅ Si tu veux un alias 'members', ajoute :
    members = relationship(
        "TontineMembers",
        overlaps="tontine_members",
        viewonly=True
    )

from app.models.currencies import Currencies
from app.models.tontinecontributions import TontineContributions
from app.models.tontinemembers import TontineMembers
from app.models.tontinepayouts import TontinePayouts
from app.models.users import Users
