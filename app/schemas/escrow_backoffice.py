from pydantic import BaseModel, Field
from decimal import Decimal

class MarkPayoutPendingRequest(BaseModel):
    payout_reference: str | None = None

class ConfirmPaidOutRequest(BaseModel):
    amount_bif: Decimal = Field(gt=0)
    payout_reference: str
    proof_type: str = "SCREENSHOT"     # SCREENSHOT/PDF/...
    proof_ref: str                      # URL S3 / id document
    proof_metadata: dict = {}
