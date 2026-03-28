import unicodedata

from app.services.assistant_intent_parser_llm import resolve_intent
from app.wallet_support_chat.schemas import WalletSupportDraft


BALANCE_DROP_WORDS = {"baisse", "baissee", "diminue", "disparu", "debite", "debitee", "sorti"}
DEPOSIT_WORDS = {"depot", "versement", "cashin", "cash", "recu", "credit"}
WITHDRAW_WORDS = {"retrait", "withdraw", "bloque", "blocke", "refuse", "pending"}
FROZEN_WORDS = {"gele", "geler", "frozen", "bloque", "suspendu", "suspendue"}
SEND_WORDS = {"envoyer", "transfert", "payer", "plus", "impossible"}
LATEST_WORDS = {"dernier", "latest", "mouvement", "operation", "transaction"}
WALLET_SUPPORT_INTENTS = {
    "balance_drop": "Ask why the wallet balance dropped or money disappeared.",
    "missing_deposit": "Report a deposit or cash-in that is missing.",
    "blocked_withdraw": "Report a blocked, refused or pending withdrawal.",
    "frozen_account": "Report or ask about a frozen or suspended account.",
    "cant_send": "Report being unable to send money or make a transfer.",
    "latest_movement": "Ask for the latest wallet transaction or movement.",
    "unknown": "The request does not match another wallet support intent.",
}


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
    resolved = resolve_intent(
        domain="wallet_support",
        message=text,
        intents=WALLET_SUPPORT_INTENTS,
        heuristic_intent=_detect_intent(text),
    )
    return WalletSupportDraft(intent=resolved.intent, raw_message=text)
