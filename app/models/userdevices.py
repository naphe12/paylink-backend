# Auto-generated from database schema
import datetime
import uuid
from typing import Optional

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserDevices(Base):
    __tablename__ = 'user_devices'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['paylink.users.user_id'], ondelete='CASCADE', name='user_devices_user_id_fkey'),
        PrimaryKeyConstraint('device_id', name='user_devices_pkey'),
        {'schema': 'paylink'}
    )

    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    device_fingerprint: Mapped[Optional[str]] = mapped_column(Text)
    push_token: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped['Users'] = relationship('Users', back_populates='user_devices')

from app.models.users import Users
