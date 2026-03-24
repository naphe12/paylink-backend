import re
import unicodedata

from app.transfer_support_chat.schemas import TransferSupportDraft


REFERENCE_PATTERN = re.compile(r"\bEXT-[A-Z0-9]{4,}\b", re.IGNORECASE)

TRACK_WORDS = {"suivre", "suivi", "statut", "ou", "où", "demande", "transfert", "reference", "reference_code"}
PENDING_WORDS = {"pending", "attente", "bloque", "bloquee", "bloquee", "raison", "pourquoi"}


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _extract_reference(message: str) -> str | None:
    match = REFERENCE_PATTERN.search(str(message or ""))
    if not match:
        return None
    return str(match.group(0)).upper()


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.replace("?", " ").split())
    if ("pending" in normalized or "attente" in normalized) and ("pourquoi" in normalized or "raison" in normalized):
        return "pending_reason"
    if tokens & PENDING_WORDS and ("pourquoi" in normalized or "raison" in normalized or "bloque" in normalized):
        return "pending_reason"
    if tokens & TRACK_WORDS or _extract_reference(message):
        return "track_transfer"
    if "status" in normalized or "statut" in normalized:
        return "status_help"
    return "unknown"


def parse_transfer_support_message(message: str) -> TransferSupportDraft:
    text = str(message or "").strip()
    return TransferSupportDraft(
        intent=_detect_intent(text),
        reference_code=_extract_reference(text),
        raw_message=text,
    )
