import re
import unicodedata

from app.p2p_chat.schemas import P2PDraft


UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    if "offre" in normalized or "mes offres" in normalized:
        return "offers_summary"
    if "pourquoi" in normalized and ("bloque" in normalized or "pending" in normalized or "attente" in normalized):
        return "why_blocked"
    if "prochaine etape" in normalized or "quoi faire" in normalized or "ensuite" in normalized:
        return "next_step"
    if "trade" in normalized or "suivi" in normalized or "reference" in normalized:
        return "track_trade"
    if "statut" in normalized or "ou en est" in normalized or "mon trade" in normalized:
        return "latest_trade"
    return "unknown"


def _extract_trade_id(message: str) -> str | None:
    match = UUID_PATTERN.search(str(message or ""))
    return match.group(0) if match else None


def parse_p2p_message(message: str) -> P2PDraft:
    text = str(message or "").strip()
    return P2PDraft(intent=_detect_intent(text), trade_id=_extract_trade_id(text), raw_message=text)
