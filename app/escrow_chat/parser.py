import re
import unicodedata

from app.escrow_chat.schemas import EscrowDraft


UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    if "pourquoi" in normalized and ("pending" in normalized or "bloque" in normalized or "attente" in normalized):
        return "why_pending"
    if (
        "prochaine etape" in normalized
        or "quoi faire" in normalized
        or "que faire" in normalized
        or "dois-je faire" in normalized
        or "etape en cours" in normalized
        or "ensuite" in normalized
    ):
        return "next_step"
    if "reference" in normalized or "commande" in normalized or "order" in normalized or "suivi" in normalized:
        return "track_order"
    if "statut" in normalized or "ou en est" in normalized or "ma demande" in normalized:
        return "latest_status"
    return "unknown"


def _extract_order_id(message: str) -> str | None:
    match = UUID_PATTERN.search(str(message or ""))
    return match.group(0) if match else None


def parse_escrow_message(message: str) -> EscrowDraft:
    text = str(message or "").strip()
    return EscrowDraft(intent=_detect_intent(text), order_id=_extract_order_id(text), raw_message=text)
