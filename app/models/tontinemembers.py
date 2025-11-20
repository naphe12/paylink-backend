# Auto-generated from database schema
import uuid

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TontineMembers(Base):
    __tablename__ = 'tontine_members'
    __table_args__ = (
        ForeignKeyConstraint(['tontine_id'], ['paylink.tontines.tontine_id'], ondelete='CASCADE', name='tontine_members_tontine_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='tontine_members_user_id_fkey'),
        PrimaryKeyConstraint('tontine_id', 'user_id', name='tontine_members_pkey'),
        UniqueConstraint('tontine_id', 'join_order', name='tontine_members_tontine_id_join_order_key'),
        {'schema': 'paylink'}
    )

    tontine_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    join_order: Mapped[int] = mapped_column(Integer, nullable=False)
    user_name: Mapped[str] = mapped_column(Text, nullable=False)   

    tontine = relationship("Tontines", back_populates="tontine_members")
    user = relationship("Users")

from app.models.tontines import Tontines
from app.models.users import Users
