import re
from decimal import Decimal, InvalidOperation

from app.agent_chat.schemas import TransferDraft


AMOUNT_PATTERNS = [
    re.compile(r"(?P<currency>\$|€)\s*(?P<amount>\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>\$|€|usd|eur|bif|xof|xaf|usdt|usdc)", re.IGNORECASE),
]
PHONE_PATTERN = re.compile(r"(\+?\d{8,15})")
PARTNER_PATTERN = re.compile(r"\b(?:via|par|sur)\s+([A-Za-z][A-Za-z .-]{1,40})", re.IGNORECASE)
RECIPIENT_PATTERN = re.compile(
    r"\b(?:a|à|to)\s+([A-Za-z][A-Za-zÀ-ÿ' -]{1,60}?)(?=\s+(?:via|par|sur|au|en)\b|$)",
    re.IGNORECASE,
)
COUNTRY_PATTERN = re.compile(r"\b(?:au|en|vers)\s+(burundi|rwanda|congo|rdc|kenya|ouganda|uganda|tanzanie)\b", re.IGNORECASE)


CURRENCY_ALIASES = {
    "$": "USD",
    "€": "EUR",
    "usd": "USD",
    "eur": "EUR",
    "bif": "BIF",
    "xof": "XOF",
    "xaf": "XAF",
    "usdt": "USDT",
    "usdc": "USDC",
}

PARTNER_ALIASES = {
    "lumicash": "Lumicash",
    "ecocash": "Ecocash",
    "enoti": "eNoti",
    "mtn": "MTN",
    "mtn mobile money": "MTN",
}

COUNTRY_ALIASES = {
    "burundi": "Burundi",
    "rwanda": "Rwanda",
    "congo": "Congo",
    "rdc": "RDC",
    "kenya": "Kenya",
    "ouganda": "Ouganda",
    "uganda": "Ouganda",
    "tanzanie": "Tanzanie",
}


def _parse_amount_and_currency(message: str) -> tuple[Decimal | None, str | None]:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        raw_amount = str(match.group("amount") or "").replace(",", ".")
        raw_currency = str(match.group("currency") or "").strip().lower()
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            return None, None
        return amount, CURRENCY_ALIASES.get(raw_currency, raw_currency.upper()[:5] or None)
    return None, None


def parse_chat_message(message: str) -> TransferDraft:
    text = str(message or "").strip()
    amount, currency = _parse_amount_and_currency(text)

    recipient_match = RECIPIENT_PATTERN.search(text)
    partner_match = PARTNER_PATTERN.search(text)
    phone_match = PHONE_PATTERN.search(text)
    country_match = COUNTRY_PATTERN.search(text)

    partner_raw = str(partner_match.group(1) or "").strip().lower() if partner_match else ""
    country_raw = str(country_match.group(1) or "").strip().lower() if country_match else ""

    return TransferDraft(
        amount=amount,
        currency=currency,
        recipient=str(recipient_match.group(1) or "").strip() if recipient_match else None,
        recipient_phone=phone_match.group(1) if phone_match else None,
        partner_name=PARTNER_ALIASES.get(partner_raw) if partner_raw else None,
        country_destination=COUNTRY_ALIASES.get(country_raw) if country_raw else None,
        raw_message=text,
    )
