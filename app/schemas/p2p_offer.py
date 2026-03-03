from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from decimal import Decimal
from typing import Any, Dict, Optional

from app.models.p2p_enums import OfferSide, PaymentMethod, TokenCode

class OfferCreate(BaseModel):
    side: OfferSide
    token: TokenCode
    price_bif_per_usd: Decimal = Field(gt=0)
    min_token_amount: Decimal = Field(gt=0)
    max_token_amount: Decimal = Field(gt=0)
    available_amount: Decimal = Field(gt=0)
    payment_method: PaymentMethod
    payment_details: Dict[str, Any] = Field(default_factory=dict)
    terms: Optional[str] = None

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalize_payment_method(cls, v):
        # Backward-compatible alias: ENOTI/eNOTI uses current enum storage ECOCASH.
        if isinstance(v, str) and v.strip().upper() == "ENOTI":
            return PaymentMethod.ECOCASH
        return v


class OfferUpdate(OfferCreate):
    pass

class OfferOut(BaseModel):
    offer_id: UUID
    user_id: UUID
    side: OfferSide
    token: TokenCode
    price_bif_per_usd: Decimal
    min_token_amount: Decimal
    max_token_amount: Decimal
    available_amount: Decimal
    payment_method: PaymentMethod
    terms: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
