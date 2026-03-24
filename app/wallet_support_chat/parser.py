import unicodedata

from app.wallet_support_chat.schemas import WalletSupportDraft


BALANCE_DROP_WORDS = {"baisse", "baissee", "diminue", "disparu", "debite", "debitee", "sorti"}
DEPOSIT_WORDS = {"depot", "versement", "cashin", "cash", "recu", "credit"}
WITHDRAW_WORDS = {"retrait", "withdraw", "bloque", "blocke", "refuse", "pending"}
FROZEN_WORDS = {"gele", "geler", "frozen", "bloque", "suspendu", "suspendue"}
SEND_WORDS = {"envoyer", "transfert", "payer", "plus", "impossible"}
LATEST_WORDS = {"dernier", "latest", "mouvement", "operation", "transaction"}


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.replace("?", " ").split())

    if (tokens & DEPOSIT_WORDS) and ("pas" in tokens or "vois" in tokens or "recois" in tokens or "recu" in tokens):
        return "missing_deposit"
    if (tokens & WITHDRAW_WORDS) and ("bloque" in normalized or "refuse" in normalized or "pending" in normalized):
        return "blocked_withdraw"
    if tokens & FROZEN_WORDS and "compte" in normalized:
        return "frozen_account"
    if (tokens & SEND_WORDS) and ("impossible" in normalized or "peux pas" in normalized or "plus" in normalized):
        return "cant_send"
    if tokens & LATEST_WORDS and ("mouvement" in normalized or "operation" in normalized or "transaction" in normalized):
        return "latest_movement"
    if ("solde" in normalized or "balance" in normalized) and (tokens & BALANCE_DROP_WORDS or "pourquoi" in normalized):
        return "balance_drop"
    return "unknown"


def parse_wallet_support_message(message: str) -> WalletSupportDraft:
    text = str(message or "").strip()
    return WalletSupportDraft(intent=_detect_intent(text), raw_message=text)
