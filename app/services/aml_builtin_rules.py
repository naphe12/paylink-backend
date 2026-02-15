from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

@dataclass
class AMLContext:
    event: str  # "P2P_CREATE" | "P2P_CRYPTO_LOCKED" | "P2P_FIAT_SENT" | "P2P_RELEASE"
    now: datetime

def rule_large_trade_bif(bif_amount: Decimal, threshold_bif: Decimal = Decimal("10000000")):
    if bif_amount >= threshold_bif:
        return ("AML_LARGE_AMOUNT", 20, {"bif_amount": str(bif_amount), "threshold": str(threshold_bif)})
    return None

def rule_unverified_kyc(kyc_status: str, who: str):
    if str(kyc_status) != "verified":
        return ("AML_KYC_NOT_VERIFIED", 15, {"who": who, "kyc_status": str(kyc_status)})
    return None

def rule_fast_repeat(trades_last_1h: int, max_trades_1h: int = 5):
    if trades_last_1h > max_trades_1h:
        return ("AML_RAPID_REPEATS", 15, {"trades_last_1h": trades_last_1h, "max": max_trades_1h})
    return None

def rule_price_outlier(diff_ratio: float, max_ratio: float = 0.10):
    if diff_ratio > max_ratio:
        return ("AML_PRICE_OUTLIER", 10, {"diff_ratio": diff_ratio, "max_ratio": max_ratio})
    return None

def rule_new_account(user_age_days: int, min_days: int = 7):
    if user_age_days < min_days:
        return ("AML_NEW_ACCOUNT", 10, {"user_age_days": user_age_days, "min_days": min_days})
    return None
