from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExternalTransferBase(BaseModel):
    partner_name: str = Field(..., example="Lumicash")
    country_destination: str = Field(..., example="Burundi")
    recipient_name: str = Field(..., example="Jean Ndayishimiye")
    recipient_phone: str = Field(..., example="+25761234567")
    amount: Decimal = Field(..., example=100.00)


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
