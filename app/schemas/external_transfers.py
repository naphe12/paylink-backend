from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ExternalTransferBase(BaseModel):
    partner_name: str = Field(..., min_length=2, max_length=80, example="Lumicash")
    country_destination: str = Field(..., example="Burundi")
    recipient_name: str = Field(..., min_length=2, max_length=120, example="Jean Ndayishimiye")
    recipient_phone: str = Field(..., min_length=8, max_length=20, pattern=r"^\+?[0-9]{8,15}$", example="+25761234567")
    amount: Decimal = Field(..., gt=Decimal("0"), le=Decimal("100000000"), example=100.00)

    @field_validator("country_destination")
    @classmethod
    def validate_country_destination(cls, value: str) -> str:
        raw = (value or "").strip()
        allowed = {
            "burundi": "Burundi",
            "rwanda": "Rwanda",
            "drc": "DRC",
            "rd congo": "DRC",
            "rdc": "DRC",
            "democratic republic of congo": "DRC",
        }
        mapped = allowed.get(raw.lower())
        if not mapped:
            raise ValueError("country_destination invalide (Burundi, Rwanda, DRC)")
        return mapped


class ExternalTransferCreate(ExternalTransferBase):
    pass


class ExternalTransferRead(ExternalTransferBase):
    transfer_id: UUID
    user_id: UUID
    currency: str
    rate: Optional[Decimal]
    local_amount: Optional[Decimal]
    credit_used: bool
    status: str
    reference_code: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ExternalBeneficiaryRead(BaseModel):
    recipient_name: str
    recipient_phone: str
    partner_name: str
    country_destination: str
