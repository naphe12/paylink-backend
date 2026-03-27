import unicodedata
import re
from datetime import date, datetime

from app.wallet_chat.schemas import WalletDraft


BALANCE_WORDS = {"solde", "balance", "wallet", "portefeuille", "combien"}
LIMIT_WORDS = {"limite", "limites", "plafond", "plafonds", "journalier", "mensuel"}
ACTIVITY_WORDS = {"mouvement", "mouvements", "historique", "recent", "recents", "activite"}
STATUS_WORDS = {"statut", "status", "compte", "gele", "bloque", "kyc"}
EXPLAIN_WORDS = {"expliquer", "explique", "explication", "details", "detail", "pourquoi"}
DATE_PATTERNS = (
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(r"\b(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})\b"),
)


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.replace("?", " ").split())
    if _extract_date(normalized) and (
        ("wallet" in normalized or "portefeuille" in normalized or "ligne de credit" in normalized or "credit line" in normalized)
        and (tokens & EXPLAIN_WORDS or tokens & ACTIVITY_WORDS)
    ):
        return "explain_movements_on_date"
    if tokens & ACTIVITY_WORDS:
        return "recent_activity"
    if tokens & LIMIT_WORDS:
        return "limits"
    if tokens & STATUS_WORDS:
        return "account_status"
    if tokens & BALANCE_WORDS:
        return "balance"
    return "unknown"


def _extract_date(normalized: str) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        try:
            return datetime(
                year=int(match.group("y")),
                month=int(match.group("m")),
                day=int(match.group("d")),
            ).date()
        except ValueError:
            return None
    return None


def _detect_scope(normalized: str) -> str:
    has_wallet = "wallet" in normalized or "portefeuille" in normalized
    has_credit = "ligne de credit" in normalized or "credit line" in normalized or "credit" in normalized
    if has_wallet and has_credit:
        return "both"
    if has_wallet:
        return "wallet"
    if has_credit:
        return "credit_line"
    return "both"


def parse_wallet_message(message: str) -> WalletDraft:
    text = str(message or "").strip()
    normalized = normalize_text(text)
    return WalletDraft(
        intent=_detect_intent(text),
        raw_message=text,
        target_date=_extract_date(normalized),
        scope=_detect_scope(normalized),
    )
