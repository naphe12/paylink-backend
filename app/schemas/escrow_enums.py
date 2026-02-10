from enum import Enum

class EscrowOrderStatus(str, Enum):
    CREATED = "CREATED"
    FUNDED = "FUNDED"
    SWAPPED = "SWAPPED"
    PAYOUT_PENDING = "PAYOUT_PENDING"
    PAID_OUT = "PAID_OUT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class EscrowNetwork(str, Enum):
    ETHEREUM = "ETHEREUM"
    POLYGON = "POLYGON"
    ARBITRUM = "ARBITRUM"
    OPTIMISM = "OPTIMISM"
    BSC = "BSC"
    TRON = "TRON"


class EscrowPayoutMethod(str, Enum):
    MOBILE_MONEY = "MOBILE_MONEY"
    BANK_TRANSFER = "BANK_TRANSFER"
