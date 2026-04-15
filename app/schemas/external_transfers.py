from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


class ExternalTransferBase(BaseModel):
    partner_name: str = Field(..., min_length=2, max_length=80, json_schema_extra={"example": "Lumicash"})
    country_destination: str = Field(..., json_schema_extra={"example": "Burundi"})
    recipient_name: str = Field(..., min_length=2, max_length=120, json_schema_extra={"example": "Jean Ndayishimiye"})
    recipient_phone: str = Field(..., json_schema_extra={"example": "+25761234567"})
    recipient_email: Optional[EmailStr] = Field(default=None, json_schema_extra={"example": "jean@example.com"})
    amount: Decimal = Field(..., gt=Decimal("0"), le=Decimal("100000000"), json_schema_extra={"example": 100.00})

    @field_validator("country_destination")
    @classmethod
    def validate_country_destination(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            raise ValueError("country_destination invalide")
        return raw


class ExternalTransferCreate(ExternalTransferBase):
    pass


class ExternalTransferRead(BaseModel):
    partner_name: str
    country_destination: str
    recipient_name: str
    recipient_phone: str | None = None
    recipient_email: Optional[EmailStr] = None
    amount: Decimal
    transfer_id: UUID
    user_id: UUID
    currency: str
    rate: Optional[Decimal]
    local_amount: Optional[Decimal]
    credit_used: bool
    status: str
    settlement_status: str | None = None
    credit_used_amount: Decimal | None = None
    credit_repaid_amount: Decimal | None = None
    credit_outstanding_amount: Decimal | None = None
    credit_repayment_status: str | None = None
    credit_repayment_updated_at: datetime | None = None
    reference_code: Optional[str]
    created_at: datetime

    @field_validator("recipient_phone", mode="before")
    @classmethod
    def normalize_recipient_phone(cls, value: str | None) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    model_config = ConfigDict(from_attributes=True)

class ExternalBeneficiaryRead(BaseModel):
    recipient_name: str
    recipient_phone: str | None = None
    recipient_email: Optional[EmailStr] = None
    partner_name: str
    country_destination: str

    @field_validator("recipient_phone", mode="before")
    @classmethod
    def normalize_recipient_phone(cls, value: str | None) -> str | None:
        raw = str(value or "").strip()
        return raw or None
