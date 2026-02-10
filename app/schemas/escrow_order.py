from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from schemas.escrow_enums import EscrowOrderStatus, EscrowNetwork, EscrowPayoutMethod


class EscrowOrderCreate(BaseModel):
    trader_id: UUID
    usdc_expected: Decimal = Field(gt=0)
    usdt_target: Decimal = Field(gt=0)
    rate_bif_usdt: Decimal = Field(gt=0)
    bif_target: Decimal = Field(gt=0)

    deposit_network: EscrowNetwork
    payout_method: EscrowPayoutMethod
    payout_account_name: str
    payout_account_number: str
    payout_provider: str


class EscrowOrderResponse(BaseModel):
    id: UUID
    status: EscrowOrderStatus
    usdc_expected: Decimal
    bif_target: Decimal
    deposit_network: EscrowNetwork
    deposit_address: str
    expires_at: datetime

    class Config:
        from_attributes = True
