from datetime import datetime

from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal
from typing import Optional, List

from app.models.p2p_enums import TradeStatus, PaymentMethod, TokenCode, OfferSide

class TradeCreate(BaseModel):
    offer_id: UUID
    token_amount: Decimal = Field(gt=0)


class MarketOrderIn(BaseModel):
    token: TokenCode
    side: OfferSide
    token_amount: Decimal = Field(gt=0)

class TradeOut(BaseModel):
    trade_id: UUID
    offer_id: UUID
    buyer_id: UUID
    seller_id: UUID
    token: TokenCode
    token_amount: Decimal
    price_bif_per_usd: Decimal
    bif_amount: Decimal
    status: TradeStatus

    escrow_network: Optional[str] = None
    escrow_deposit_addr: Optional[str] = None
    escrow_deposit_ref: Optional[str] = None
    escrow_provider: Optional[str] = None
    escrow_tx_hash: Optional[str] = None
    escrow_lock_log_index: Optional[int] = None

    payment_method: PaymentMethod
    risk_score: int
    flags: List[str]
    fiat_sent_at: Optional[datetime] = None
    fiat_confirmed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class FiatSentIn(BaseModel):
    proof_url: str
    note: Optional[str] = None

class DisputeOpenIn(BaseModel):
    reason: str = Field(min_length=5)
