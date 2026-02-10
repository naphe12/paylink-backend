from pydantic import BaseModel
from decimal import Decimal

class EscrowPayoutConfirm(BaseModel):
    reference: str
    amount_bif: Decimal
