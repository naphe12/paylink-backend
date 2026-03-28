import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.services.assistant_intent_parser_llm import resolve_intent
from app.credit_chat.schemas import CreditDraft


AMOUNT_PATTERNS = [
    re.compile(
        r"(?P<currency>\$|EUR|USD|BIF|XOF|XAF|USDT|USDC|CFA|FCFA)\s*(?P<amount>\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>\$|EUR|USD|BIF|XOF|XAF|USDT|USDC|CFA|FCFA)",
        re.IGNORECASE,
    ),
]

CURRENCY_ALIASES = {
    "$": "USD",
    "usd": "USD",
    "eur": "EUR",
    "bif": "BIF",
    "fbu": "BIF",
    "xof": "XOF",
    "xaf": "XAF",
    "usdt": "USDT",
    "usdc": "USDC",
    "cfa": "XOF",
    "fcfa": "XAF",
}

CAPACITY_WORDS = {"capacite", "credit", "reste", "disponible", "wallet", "solde"}
SIMULATE_WORDS = {"si", "envoie", "transfert", "envoyer", "passe", "possible", "peut", "retrait"}
PENDING_WORDS = {"pending", "attente", "bloque", "pourquoi"}
CREDIT_INTENTS = {
    "capacity": "Ask how much credit or capacity is available.",
    "simulate_transfer": "Ask to simulate whether a transfer, withdrawal or send would be possible.",
    "pending_reason": "Ask why a credit-related operation is pending or blocked.",
    "unknown": "The request does not match another credit intent.",
}


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _parse_amount_and_currency(message: str) -> tuple[Decimal | None, str | None]:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        raw_amount = str(match.group("amount") or "").replace(",", ".")
        raw_currency = normalize_text(match.group("currency"))
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            return None, None
        return amount, CURRENCY_ALIASES.get(raw_currency, raw_currency.upper()[:5] or None)
    return None, None


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.split())
    if ("pending" in normalized or "attente" in normalized) and ("pourquoi" in normalized or "raison" in normalized):
        return "pending_reason"
    if tokens & PENDING_WORDS and ("pourquoi" in normalized or "raison" in normalized):
        return "pending_reason"
    if any(term in normalized for term in SIMULATE_WORDS):
        return "simulate_transfer"
    if any(term in normalized for term in CAPACITY_WORDS):
        return "capacity"
    return "unknown"


def parse_credit_message(message: str) -> CreditDraft:
    text = str(message or "").strip()
    amount, currency = _parse_amount_and_currency(text)
    resolved = resolve_intent(domain="credit", message=text, intents=CREDIT_INTENTS, heuristic_intent=_detect_intent(text))
    return CreditDraft(
        intent=resolved.intent,
        amount=amount,
        currency=currency,
        raw_message=text,
    )
