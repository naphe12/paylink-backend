import uuid

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.users import Users  # si tu as back_populates
from sqlalchemy import (
    Column, Numeric, CHAR, Enum, DateTime, Text, ForeignKeyConstraint,
    PrimaryKeyConstraint, CheckConstraint, Index, text
)

class BonusHistory(Base):
    __tablename__ = "bonus_history"
    __table_args__ = (
        PrimaryKeyConstraint('id', name='bonus_history_pkey'),
        {'schema': 'paylink'}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)

    # Montant du bonus en BIF ajouté ou utilisé
    amount_bif = Column(Numeric(12, 2), nullable=False)

    # earned  → bonus gagné
    # used    → bonus dépensé
    source = Column(String(20), nullable=False)  

    # Id du transfert source (ex: transfert externe -> earned)
    # ou id de transaction bonus send -> used
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relation optionnelle (lecture)
    user = relationship("Users", back_populates="bonus_history")
