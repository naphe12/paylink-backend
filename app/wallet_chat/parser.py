from app.services.assistant_semantic_parser import (
    SemanticQuery,
    extract_date_range,
    extract_single_date,
    has_any_term,
    normalize_text,
    tokenize,
)
from app.wallet_chat.schemas import WalletDraft


BALANCE_WORDS = {"solde", "balance", "wallet", "portefeuille", "combien"}
LIMIT_WORDS = {"limite", "limites", "plafond", "plafonds", "journalier", "mensuel"}
ACTIVITY_WORDS = {"mouvement", "mouvements", "historique", "recent", "recents", "activite"}
STATUS_WORDS = {"statut", "status", "compte", "gele", "bloque", "kyc", "situation"}
EXPLAIN_WORDS = {"expliquer", "explique", "explication", "details", "detail", "pourquoi"}


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


def _build_wallet_semantic_query(message: str) -> SemanticQuery:
    normalized = normalize_text(message)
    tokens = tokenize(normalized)
    exact_date = extract_single_date(normalized)
    date_from, date_to = extract_date_range(normalized)
    subject = _detect_scope(normalized)
    query = SemanticQuery(
        domain="wallet",
        raw_message=str(message or "").strip(),
        normalized_message=normalized,
        tokens=tokens,
        subject=subject,
        exact_date=exact_date,
        date_from=date_from,
        date_to=date_to,
    )

    if "ligne de credit" in normalized or "credit line" in normalized:
        query.matched_signals.append("credit_line_subject")
    if "wallet" in normalized or "portefeuille" in normalized:
        query.matched_signals.append("wallet_subject")
    if tokens & EXPLAIN_WORDS:
        query.explanation_mode = "causal"
        query.matched_signals.append("explain_words")
    elif tokens & ACTIVITY_WORDS:
        query.explanation_mode = "descriptive"
        query.matched_signals.append("activity_words")

    if exact_date and subject in {"wallet", "credit_line", "both"} and (tokens & EXPLAIN_WORDS or tokens & ACTIVITY_WORDS):
        query.action = "explain_movements_on_date"
        return query
    if subject == "credit_line":
        query.action = "account_status"
        return query
    if tokens & ACTIVITY_WORDS:
        query.action = "recent_activity"
        return query
    if tokens & LIMIT_WORDS:
        query.action = "limits"
        return query
    if tokens & STATUS_WORDS:
        query.action = "account_status"
        return query
    if has_any_term(normalized, BALANCE_WORDS):
        query.action = "balance"
        return query

    return query


def parse_wallet_message(message: str) -> WalletDraft:
    text = str(message or "").strip()
    query = _build_wallet_semantic_query(text)
    return WalletDraft(
        intent=query.action,
        raw_message=text,
        target_date=query.exact_date,
        scope=query.subject or "both",
        semantic_hints=query.to_dict(),
    )
