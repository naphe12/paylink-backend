import hmac
import hashlib

def verify_hmac_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    mac = hmac.new(secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
    # signature attendue: hex
    return hmac.compare_digest(mac, signature)
