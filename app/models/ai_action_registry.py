from sqlalchemy import Boolean, Column, ForeignKey, Text, text

from app.core.database import Base


class AiActionRegistry(Base):
    __tablename__ = "ai_action_registry"
    __table_args__ = {"schema": "ia"}

    action_code = Column(Text, primary_key=True)
    intent_code = Column(Text, ForeignKey("ia.ai_intents.intent_code", ondelete="CASCADE"), nullable=False)
    service_name = Column(Text, nullable=False)
    method_name = Column(Text, nullable=False)
    confirmation_template = Column(Text)
    success_template = Column(Text)
    failure_template = Column(Text)
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
