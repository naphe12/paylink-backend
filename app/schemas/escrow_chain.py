from pydantic import BaseModel
from decimal import Decimal
from schemas.escrow_enums import EscrowNetwork

class ChainDepositWebhook(BaseModel):
    network: EscrowNetwork
    tx_hash: str
    from_address: str
    to_address: str
    amount: Decimal
    confirmations: int
