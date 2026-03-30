from sqlalchemy import Boolean, Column, Text, text

from app.core.database import Base


class AiIntents(Base):
    __tablename__ = "ai_intents"
    __table_args__ = {"schema": "ia"}

    intent_code = Column(Text, primary_key=True)
    label = Column(Text, nullable=False)
    description = Column(Text)
    domain = Column(Text, nullable=False)
    requires_confirmation = Column(Boolean, nullable=False, server_default=text("true"))
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
