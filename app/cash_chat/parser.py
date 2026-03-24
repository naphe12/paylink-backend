import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.cash_chat.schemas import CashDraft


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
PHONE_PATTERN = re.compile(r"(\+?\d{8,15})")

CURRENCY_ALIASES = {
    "$": "USD",
    "usd": "USD",
    "eur": "EUR",
    "bif": "BIF",
    "xof": "XOF",
    "xaf": "XAF",
    "usdt": "USDT",
    "usdc": "USDC",
    "cfa": "XOF",
    "fcfa": "XAF",
}

PROVIDER_ALIASES = {
    "lumicash": "Lumicash",
    "lumi cash": "Lumicash",
    "lumi": "Lumicash",
    "ecocash": "Ecocash",
    "eco cash": "Ecocash",
    "enoti": "eNoti",
    "mtn": "MTN",
    "mtn mobile money": "MTN",
}

DEPOSIT_WORDS = {"depot", "deposer", "cashin", "cash-in", "cash in", "recharger", "recharge"}
WITHDRAW_WORDS = {"retrait", "retirer", "cashout", "cash-out", "cash out"}
CAPACITY_WORDS = {"capacite", "solde", "combien", "disponible", "wallet", "credit"}
STATUS_WORDS = {"statut", "status", "demande", "pending", "approuvee", "approuve", "rejetee", "rejet", "completee", "complete"}


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


def _find_provider(message: str) -> str | None:
    normalized = f" {normalize_text(message)} "
    for alias, provider in sorted(PROVIDER_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return provider
    return None


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.split())
    if ("demande" in normalized or "retrait" in normalized or "depot" in normalized) and (
        "statut" in normalized or "status" in normalized or "pending" in normalized
    ):
        return "request_status"
    if any(term in normalized for term in STATUS_WORDS) and "demande" in normalized:
        return "request_status"
    if any(term in normalized for term in DEPOSIT_WORDS) or tokens & DEPOSIT_WORDS:
        return "deposit"
    if any(term in normalized for term in WITHDRAW_WORDS) or tokens & WITHDRAW_WORDS:
        return "withdraw"
    if any(term in normalized for term in CAPACITY_WORDS) or tokens & CAPACITY_WORDS:
        return "capacity"
    return "unknown"


def parse_cash_message(message: str) -> CashDraft:
    text = str(message or "").strip()
    amount, currency = _parse_amount_and_currency(text)
    phone_match = PHONE_PATTERN.search(text)
    return CashDraft(
        intent=_detect_intent(text),
        amount=amount,
        currency=currency,
        mobile_number=phone_match.group(1) if phone_match else None,
        provider_name=_find_provider(text),
        raw_message=text,
    )
