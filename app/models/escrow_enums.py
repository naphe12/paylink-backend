import enum

class EscrowOrderStatus(str, enum.Enum):
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


class EscrowNetwork(str, enum.Enum):
    ETHEREUM = "ETHEREUM"
    POLYGON = "POLYGON"
    ARBITRUM = "ARBITRUM"
    OPTIMISM = "OPTIMISM"
    BSC = "BSC"
    SOLANA = "SOLANA"
    TRON = "TRON"
    OTHER = "OTHER"


class EscrowPayoutMethod(str, enum.Enum):
    MOBILE_MONEY = "MOBILE_MONEY"
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH = "CASH"
    OTHER = "OTHER"


class EscrowProofType(str, enum.Enum):
    SCREENSHOT = "SCREENSHOT"
    PDF = "PDF"
    RECEIPT_ID = "RECEIPT_ID"
    BANK_REFERENCE = "BANK_REFERENCE"
    OTHER = "OTHER"


class EscrowConversionMode(str, enum.Enum):
    INVENTORY_INTERNAL = "INVENTORY_INTERNAL"
    CEX = "CEX"
    DEX = "DEX"
    MANUAL = "MANUAL"


class EscrowActorType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    OPERATOR = "OPERATOR"
    TRADER = "TRADER"
