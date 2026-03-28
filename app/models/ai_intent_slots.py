from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AiIntentSlots(Base):
    __tablename__ = "ai_intent_slots"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intent_code = Column(Text, ForeignKey("ia.ai_intents.intent_code", ondelete="CASCADE"), nullable=False)
    slot_name = Column(Text, nullable=False)
    slot_type = Column(Text, nullable=False)
    required = Column(Boolean, nullable=False, server_default=text("true"))
    position_hint = Column(Integer)
    validation_rule = Column(Text)
    example = Column(Text)
