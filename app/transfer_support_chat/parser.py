from app.services.assistant_semantic_parser import (
    SemanticQuery,
    extract_transfer_reference,
    has_any_term,
    normalize_text,
    tokenize,
)
from app.transfer_support_chat.schemas import TransferSupportDraft


TRACK_WORDS = {"suivre", "suivi", "statut", "ou", "demande", "transfert", "reference", "reference_code"}
PENDING_WORDS = {"pending", "attente", "bloque", "bloquee", "raison", "pourquoi"}
CAPACITY_WORDS = {"capacite", "capacite financiere", "credit", "disponible", "wallet", "solde", "utiliser", "peut"}


def _build_transfer_semantic_query(message: str) -> SemanticQuery:
    normalized = normalize_text(message)
    tokens = tokenize(normalized)
    reference_code = extract_transfer_reference(message)
    query = SemanticQuery(
        domain="transfer_support",
        raw_message=str(message or "").strip(),
        normalized_message=normalized,
        tokens=tokens,
        reference_code=reference_code,
    )

    if reference_code:
        query.matched_signals.append("reference_code")

    if has_any_term(normalized, CAPACITY_WORDS):
        query.action = "capacity"
        query.subject = "financial_capacity"
        query.matched_signals.append("capacity_words")
        return query

    if ("pending" in normalized or "attente" in normalized) and ("pourquoi" in normalized or "raison" in normalized):
        query.action = "pending_reason"
        query.explanation_mode = "causal"
        query.matched_signals.append("pending_reason_phrase")
        return query

    if tokens & PENDING_WORDS and ("pourquoi" in normalized or "raison" in normalized or "bloque" in normalized):
        query.action = "pending_reason"
        query.explanation_mode = "causal"
        query.matched_signals.append("pending_reason_tokens")
        return query

    if "status" in normalized or "statut" in normalized:
        query.action = "status_help"
        query.subject = "status_catalog"
        query.matched_signals.append("status_help")
        return query

    if tokens & TRACK_WORDS or reference_code:
        query.action = "track_transfer"
        query.subject = "transfer_request"
        query.matched_signals.append("tracking_words")
        return query

    return query


def parse_transfer_support_message(message: str) -> TransferSupportDraft:
    text = str(message or "").strip()
    query = _build_transfer_semantic_query(text)
    return TransferSupportDraft(
        intent=query.action,
        reference_code=query.reference_code,
        raw_message=text,
        semantic_hints=query.to_dict(),
    )
