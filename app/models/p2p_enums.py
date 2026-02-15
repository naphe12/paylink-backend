import enum

class OfferSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class TradeStatus(str, enum.Enum):
    CREATED = "CREATED"
    AWAITING_CRYPTO = "AWAITING_CRYPTO"
    CRYPTO_LOCKED = "CRYPTO_LOCKED"
    AWAITING_FIAT = "AWAITING_FIAT"
    FIAT_SENT = "FIAT_SENT"
    FIAT_CONFIRMED = "FIAT_CONFIRMED"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"

class PaymentMethod(str, enum.Enum):
    LUMICASH = "LUMICASH"
    ECOCASH = "ECOCASH"
    BANK = "BANK"
    CASH = "CASH"
    OTHER = "OTHER"

class DisputeStatus(str, enum.Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED_BUYER = "RESOLVED_BUYER"
    RESOLVED_SELLER = "RESOLVED_SELLER"
    CLOSED = "CLOSED"

class TokenCode(str, enum.Enum):
    USDC = "USDC"
    USDT = "USDT"
