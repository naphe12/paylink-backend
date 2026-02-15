from sqlalchemy import Column, Text, Boolean, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text

from app.core.database import Base

class AMLRule(Base):
    __tablename__ = "rules"
    __table_args__ = ({"schema": "aml"},)

    rule_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    severity = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
