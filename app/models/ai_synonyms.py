from sqlalchemy import Boolean, Column, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AiSynonyms(Base):
    __tablename__ = "ai_synonyms"
    __table_args__ = {"schema": "ia"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    domain = Column(Text, nullable=False)
    canonical_value = Column(Text, nullable=False)
    synonym = Column(Text, nullable=False)
    language_code = Column(Text, nullable=False, server_default=text("'fr'"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
