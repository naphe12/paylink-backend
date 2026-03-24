import unicodedata

from app.wallet_chat.schemas import WalletDraft


BALANCE_WORDS = {"solde", "balance", "wallet", "portefeuille", "combien"}
LIMIT_WORDS = {"limite", "limites", "plafond", "plafonds", "journalier", "mensuel"}
ACTIVITY_WORDS = {"mouvement", "mouvements", "historique", "recent", "recents", "activite"}
STATUS_WORDS = {"statut", "status", "compte", "gele", "bloque", "kyc"}


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.replace("?", " ").split())
    if tokens & ACTIVITY_WORDS:
        return "recent_activity"
    if tokens & LIMIT_WORDS:
        return "limits"
    if tokens & STATUS_WORDS:
        return "account_status"
    if tokens & BALANCE_WORDS:
        return "balance"
    return "unknown"


def parse_wallet_message(message: str) -> WalletDraft:
    text = str(message or "").strip()
    return WalletDraft(intent=_detect_intent(text), raw_message=text)
