import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.agent_chat.schemas import TransferDraft


AMOUNT_PATTERNS = [
    re.compile(r"(?P<currency>\$|EUR|USD|BIF|XOF|XAF|USDT|USDC|CFA|FCFA)\s*(?P<amount>\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>\$|€|EUR|USD|BIF|XOF|XAF|USDT|USDC|CFA|FCFA)", re.IGNORECASE),
]
PHONE_PATTERN = re.compile(r"(\+?\d{8,15})")
PARTNER_PATTERN = re.compile(
    r"\b(?:via|par|sur)\s+(lumicash|ecocash|enoti|mtn(?: mobile money)?)\b",
    re.IGNORECASE,
)
RECIPIENT_START_PATTERN = re.compile(r"\b(?:a|à|to|pour)\b", re.IGNORECASE)
COUNTRY_PATTERN = re.compile(
    r"\b(?:au|en|vers)\s+(burundi|rwanda|congo|rdc|kenya|ouganda|uganda|tanzanie)\b",
    re.IGNORECASE,
)


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
    "cfa": "XOF",
    "fcfa": "XAF",
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

RECIPIENT_STOP_WORDS = {
    "via",
    "par",
    "sur",
    "au",
    "en",
    "vers",
    "avec",
    "pour",
}

RECIPIENT_ALLOWED_PARTICLES = {
    "de",
    "du",
    "des",
    "la",
    "le",
    "van",
    "von",
    "bin",
    "ibn",
    "di",
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


def _clean_recipient_value(value: str | None) -> str | None:
    raw = str(value or "").strip(" ,.;:-")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw or None


def _extract_recipient_name(message: str) -> str | None:
    start_match = RECIPIENT_START_PATTERN.search(message)
    if not start_match:
        return None

    tail = message[start_match.end():].strip()
    if not tail:
        return None

    tokens = re.split(r"\s+", tail)
    captured: list[str] = []
    for token in tokens:
        cleaned = token.strip(" ,.;:-")
        if not cleaned:
            continue
        normalized = normalize_text(cleaned)
        if normalized in RECIPIENT_STOP_WORDS and captured:
            break
        if normalized in RECIPIENT_STOP_WORDS and not captured:
            continue
        if PHONE_PATTERN.fullmatch(cleaned):
            break
        if re.fullmatch(r"\d+(?:[.,]\d+)?", cleaned):
            break

        starts_like_name = bool(re.match(r"^[A-Za-zÀ-ÿ]", cleaned))
        allowed_particle = normalized in RECIPIENT_ALLOWED_PARTICLES
        if not starts_like_name and not allowed_particle:
            break

        captured.append(cleaned)
        if len(" ".join(captured)) >= 80:
            break

    return _clean_recipient_value(" ".join(captured))


def parse_chat_message(message: str) -> TransferDraft:
    text = str(message or "").strip()
    amount, currency = _parse_amount_and_currency(text)

    partner_match = PARTNER_PATTERN.search(text)
    phone_match = PHONE_PATTERN.search(text)
    country_match = COUNTRY_PATTERN.search(text)

    partner_raw = normalize_text(partner_match.group(1)) if partner_match else ""
    country_raw = normalize_text(country_match.group(1)) if country_match else ""

    return TransferDraft(
        amount=amount,
        currency=currency,
        recipient=_extract_recipient_name(text),
        recipient_phone=phone_match.group(1) if phone_match else None,
        partner_name=PARTNER_ALIASES.get(partner_raw) if partner_raw else None,
        country_destination=COUNTRY_ALIASES.get(country_raw) if country_raw else None,
        raw_message=text,
    )
