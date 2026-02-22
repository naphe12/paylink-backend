import hmac
import hashlib
import os


def compute_signature(raw_body: bytes) -> str:
    secret = os.getenv("HMAC_SECRET")
    if not secret:
        raise RuntimeError("Missing env HMAC_SECRET")

    mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
    return mac.hexdigest()
