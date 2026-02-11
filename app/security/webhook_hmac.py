import hmac
import hashlib
from app.config import settings

def compute_signature(raw_body: bytes) -> str:
    return hmac.new(
        settings.ESCROW_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = compute_signature(raw_body)
    return hmac.compare_digest(expected, signature or "")
