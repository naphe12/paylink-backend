from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SupportCaseAttachments(Base):
    __tablename__ = "support_case_attachments"
    __table_args__ = (
        CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0",
            name="support_case_attachments_file_size_non_negative",
        ),
        {"schema": "product_support"},
    )

    attachment_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id = Column(UUID(as_uuid=True), ForeignKey("product_support.support_cases.case_id", ondelete="CASCADE"), nullable=False)
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="SET NULL"))
    file_name = Column(Text, nullable=False)
    file_mime_type = Column(Text)
    file_size_bytes = Column(BigInteger)
    storage_key = Column(Text, nullable=False)
    checksum_sha256 = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
