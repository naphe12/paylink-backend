import unicodedata

from app.kyc_chat.schemas import KycDraft


STATUS_WORDS = {"kyc", "statut", "status", "niveau", "tier", "identite"}
MISSING_DOCS_WORDS = {"document", "documents", "piece", "pieces", "manque", "manquant", "requis"}
LIMIT_WORDS = {"limite", "limites", "plafond", "plafonds", "journalier", "mensuel"}
UPGRADE_WORDS = {"upgrade", "niveau", "suivant", "debloque", "change", "ameliore", "faire", "completer"}


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    tokens = set(normalized.replace("?", " ").split())

    if tokens & MISSING_DOCS_WORDS and ("document" in normalized or "manque" in normalized or "piece" in normalized):
        return "missing_docs"
    if tokens & LIMIT_WORDS:
        return "limits"
    if (
        "niveau suivant" in normalized
        or "si je fais mon kyc" in normalized
        or "si je complete mon kyc" in normalized
        or "qu est ce qui change" in normalized
        or "qu'est ce qui change" in str(message or "").lower()
        or tokens & UPGRADE_WORDS and "kyc" in normalized
    ):
        return "upgrade_benefits"
    if tokens & STATUS_WORDS or "pourquoi je suis limite" in normalized or "pourquoi mon compte est limite" in normalized:
        return "status"
    return "unknown"


def parse_kyc_message(message: str) -> KycDraft:
    text = str(message or "").strip()
    return KycDraft(
        intent=_detect_intent(text),
        raw_message=text,
    )
