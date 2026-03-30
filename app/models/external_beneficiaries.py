from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ExternalBeneficiaries(Base):
    __tablename__ = "external_beneficiaries"
    __table_args__ = (
        Index(
            "uq_external_beneficiaries_user_partner_phone_account",
            "user_id",
            "partner_name",
            "recipient_phone",
            text("coalesce(lower(recipient_email), '')"),
            unique=True,
        ),
        {"schema": "paylink"},
    )

    beneficiary_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("paylink.users.user_id", ondelete="CASCADE"), nullable=False)
    recipient_name = Column(Text, nullable=False)
    recipient_phone = Column(Text, nullable=False)
    recipient_email = Column(Text)
    partner_name = Column(Text, nullable=False)
    country_destination = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
