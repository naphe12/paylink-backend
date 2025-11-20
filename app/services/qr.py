import hmac
import hashlib
import base64
from app.core.config import settings

def sign_uid(user_id: str) -> str:
    secret = settings.QR_SECRET.encode()
    msg = user_id.encode()
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode()
def verify_qr(uid: str, sig: str) -> bool:
    expected = sign_uid(uid)
    return hmac.compare_digest(expected, sig)
