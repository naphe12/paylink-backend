# app/models/security_logs.py

from sqlalchemy import Column, String, Enum, JSON, TIMESTAMP, func,text
from app.core.database import Base
import enum
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import *
class SecuritySeverity(enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"

class SecurityLogs(Base):
    __tablename__ = "security_logs"
    __table_args__ = {"schema": "paylink"}
    #log_id = Column(uuid.UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    log_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), nullable=True)
    event_type = Column(String, nullable=False)
    severity = Column(Enum(SecuritySeverity), default="info")
    message = Column(String, nullable=False)
    metadata_ = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
