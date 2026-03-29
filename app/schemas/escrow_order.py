from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from schemas.escrow_enums import EscrowOrderStatus, EscrowNetwork, EscrowPayoutMethod
from app.schemas.dispute_codes import (
    EscrowRefundReasonCode,
    EscrowRefundResolutionCode,
    ProofTypeCode,
)


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

    model_config = ConfigDict(from_attributes=True)


class EscrowRefundRequestIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    reason_code: EscrowRefundReasonCode | None = None
    proof_type: ProofTypeCode | None = None
    proof_ref: str | None = Field(default=None, min_length=1, max_length=500)


class EscrowRefundConfirmIn(BaseModel):
    resolution: str = Field(min_length=3, max_length=500)
    resolution_code: EscrowRefundResolutionCode | None = None
    proof_type: ProofTypeCode | None = None
    proof_ref: str | None = Field(default=None, min_length=1, max_length=500)
