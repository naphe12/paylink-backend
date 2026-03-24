from decimal import Decimal
from difflib import SequenceMatcher
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_chat.parser import normalize_text, parse_chat_message
from app.agent_chat.schemas import ChatResponse, TransferDraft
from app.models.external_transfers import ExternalTransfers
from app.models.wallets import Wallets
from app.models.credit_lines import CreditLines


SUPPORTED_TRANSFER_PARTNERS = {"Lumicash", "Ecocash", "eNoti"}


async def _get_wallet_context(db: AsyncSession, user_id) -> dict:
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    credit_line = await db.scalar(
        select(CreditLines)
        .where(CreditLines.user_id == user_id, CreditLines.deleted_at.is_(None))
        .order_by(CreditLines.created_at.desc())
    )
    wallet_currency = str(getattr(wallet, "currency_code", "") or "").upper() or None
    wallet_available = Decimal(getattr(wallet, "available", 0) or 0)
    credit_available = (
        max(Decimal(getattr(credit_line, "outstanding_amount", 0) or 0), Decimal("0"))
        if credit_line
        else Decimal("0")
    )
    return {
        "wallet_currency": wallet_currency,
        "wallet_available": wallet_available,
        "credit_available": credit_available,
        "total_capacity": wallet_available + credit_available,
    }


async def _get_recent_beneficiaries(db: AsyncSession, user_id) -> list[dict]:
    rows = (
        await db.execute(
            select(
                ExternalTransfers.recipient_name,
                ExternalTransfers.recipient_phone,
                ExternalTransfers.partner_name,
                ExternalTransfers.country_destination,
            )
            .where(ExternalTransfers.user_id == user_id)
            .order_by(ExternalTransfers.created_at.desc())
            .limit(20)
        )
    ).all()
    items = []
    seen = set()
    for row in rows:
        key = (
            str(row.recipient_name or "").strip().lower(),
            str(row.recipient_phone or "").strip(),
            str(row.partner_name or "").strip().lower(),
            str(row.country_destination or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "recipient_name": str(row.recipient_name or "").strip(),
                "recipient_phone": str(row.recipient_phone or "").strip(),
                "partner_name": str(row.partner_name or "").strip(),
                "country_destination": str(row.country_destination or "").strip(),
            }
        )
    return items


async def _get_recent_chat_memories(db: AsyncSession, user_id) -> list[dict]:
    transfers = (
        await db.execute(
            select(ExternalTransfers)
            .where(ExternalTransfers.user_id == user_id)
            .order_by(ExternalTransfers.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    memories: list[dict] = []
    seen = set()
    for transfer in transfers:
        metadata = dict(getattr(transfer, "metadata_", {}) or {})
        chat_memory = metadata.get("chat_memory") or {}
        if not isinstance(chat_memory, dict):
            continue
        raw_message = str(chat_memory.get("raw_message") or "").strip()
        recipient_alias = str(chat_memory.get("recipient_input") or "").strip()
        recipient_name = str(chat_memory.get("recipient_name") or transfer.recipient_name or "").strip()
        if not raw_message and not recipient_alias:
            continue
        key = (
            normalize_text(raw_message),
            normalize_text(recipient_alias),
            normalize_text(recipient_name),
        )
        if key in seen:
            continue
        seen.add(key)
        memories.append(
            {
                "raw_message": raw_message,
                "recipient_input": recipient_alias,
                "recipient_name": recipient_name,
                "recipient_phone": str(chat_memory.get("recipient_phone") or transfer.recipient_phone or "").strip(),
                "partner_name": str(chat_memory.get("partner_name") or transfer.partner_name or "").strip(),
                "country_destination": str(
                    chat_memory.get("country_destination") or transfer.country_destination or ""
                ).strip(),
            }
        )
    return memories


def _tokenize_name(value: str | None) -> set[str]:
    normalized = normalize_text(value)
    return {
        token
        for token in normalized.split()
        if token and len(token) >= 2
    }


def _score_beneficiary_match(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    sequence_score = SequenceMatcher(None, query_norm, candidate_norm).ratio()

    query_tokens = _tokenize_name(query)
    candidate_tokens = _tokenize_name(candidate)
    overlap_score = 0.0
    if query_tokens and candidate_tokens:
        common = len(query_tokens & candidate_tokens)
        overlap_score = common / max(len(query_tokens), len(candidate_tokens))

    contains_score = 0.0
    if query_norm and (query_norm in candidate_norm or candidate_norm in query_norm):
        contains_score = 1.0

    return max(sequence_score, overlap_score, contains_score * 0.96)


def _resolve_beneficiary_from_history(
    draft: TransferDraft,
    beneficiaries: list[dict],
) -> tuple[TransferDraft, list[str]]:
    assumptions: list[str] = []
    if not draft.recipient:
        return draft, assumptions

    recipient_norm = normalize_text(draft.recipient)
    best = None
    best_score = 0.0
    for item in beneficiaries:
        candidate = str(item["recipient_name"] or "").strip()
        score = _score_beneficiary_match(recipient_norm, candidate)
        if score > best_score:
            best = item
            best_score = score

    if not best or best_score < 0.6:
        return draft, assumptions

    draft.recognized_beneficiary = True
    if not draft.recipient_phone and best.get("recipient_phone"):
        draft.recipient_phone = best["recipient_phone"]
        assumptions.append(f"Telephone repris du beneficiaire habituel {best['recipient_name']}.")
    if not draft.partner_name and best.get("partner_name"):
        draft.partner_name = best["partner_name"]
        assumptions.append(f"Partenaire repris depuis l'historique: {best['partner_name']}.")
    if not draft.country_destination and best.get("country_destination"):
        draft.country_destination = best["country_destination"]
        assumptions.append(f"Pays repris depuis l'historique: {best['country_destination']}.")
    return draft, assumptions


def _apply_defaults(draft: TransferDraft) -> list[str]:
    assumptions: list[str] = []
    if draft.country_destination == "Burundi" and not draft.partner_name:
        draft.partner_name = "Lumicash"
        assumptions.append("Partenaire par defaut applique pour Burundi: Lumicash.")
    return assumptions


def _learn_from_history(draft: TransferDraft, beneficiaries: list[dict]) -> list[str]:
    assumptions: list[str] = []
    if not beneficiaries:
        return assumptions

    if not draft.recipient and draft.partner_name and draft.country_destination:
        for item in beneficiaries:
            if (
                str(item.get("partner_name") or "").strip() == str(draft.partner_name or "").strip()
                and str(item.get("country_destination") or "").strip() == str(draft.country_destination or "").strip()
                and item.get("recipient_name")
            ):
                assumptions.append(
                    "J'ai reconnu votre couple partenaire/pays habituel, mais il me faut toujours le beneficiaire."
                )
                break

    if draft.recipient and (not draft.partner_name or not draft.country_destination):
        best = None
        best_score = 0.0
        for item in beneficiaries:
            candidate = str(item.get("recipient_name") or "").strip()
            if not candidate:
                continue
            score = _score_beneficiary_match(draft.recipient, candidate)
            if score > best_score:
                best = item
                best_score = score

        if best and best_score >= 0.6:
            if not draft.partner_name and best.get("partner_name"):
                draft.partner_name = str(best["partner_name"]).strip()
                assumptions.append(f"Partenaire appris depuis vos envois precedents: {draft.partner_name}.")
            if not draft.country_destination and best.get("country_destination"):
                draft.country_destination = str(best["country_destination"]).strip()
                assumptions.append(
                    f"Pays appris depuis vos envois precedents: {draft.country_destination}."
                )

    return assumptions


def _learn_from_memories(
    draft: TransferDraft,
    *,
    raw_message: str,
    memories: list[dict],
) -> list[str]:
    assumptions: list[str] = []
    if not memories:
        return assumptions

    raw_norm = normalize_text(raw_message)
    best = None
    best_score = 0.0
    for item in memories:
        scores = [
            _score_beneficiary_match(raw_norm, str(item.get("raw_message") or "")),
            _score_beneficiary_match(raw_norm, str(item.get("recipient_input") or "")),
        ]
        if draft.recipient:
            scores.append(_score_beneficiary_match(draft.recipient, str(item.get("recipient_input") or "")))
            scores.append(_score_beneficiary_match(draft.recipient, str(item.get("recipient_name") or "")))
        score = max(scores)
        if score > best_score:
            best = item
            best_score = score

    if not best or best_score < 0.72:
        return assumptions

    learned_from = str(best.get("recipient_input") or best.get("recipient_name") or "").strip()
    if not draft.recipient and best.get("recipient_name"):
        draft.recipient = str(best["recipient_name"]).strip()
        assumptions.append(f"Beneficiaire appris depuis votre formulation habituelle: {draft.recipient}.")
    if not draft.recipient_phone and best.get("recipient_phone"):
        draft.recipient_phone = str(best["recipient_phone"]).strip()
        assumptions.append(f"Numero appris depuis vos confirmations precedentes pour {learned_from}.")
    if not draft.partner_name and best.get("partner_name"):
        draft.partner_name = str(best["partner_name"]).strip()
        assumptions.append(f"Partenaire appris depuis vos confirmations precedentes: {draft.partner_name}.")
    if not draft.country_destination and best.get("country_destination"):
        draft.country_destination = str(best["country_destination"]).strip()
        assumptions.append(
            f"Pays appris depuis vos confirmations precedentes: {draft.country_destination}."
        )
    return assumptions


def _missing_fields_for_confirmation(draft: TransferDraft) -> list[str]:
    missing = []
    if draft.amount is None or draft.amount <= Decimal("0"):
        missing.append("amount")
    if not draft.currency:
        missing.append("currency")
    if not draft.recipient:
        missing.append("recipient")
    return missing


def _missing_fields_for_execution(draft: TransferDraft) -> list[str]:
    missing = []
    if not draft.partner_name:
        missing.append("partner_name")
    if not draft.country_destination:
        missing.append("country_destination")
    if not draft.recipient_phone:
        missing.append("recipient_phone")
    return missing


def _find_short_phone_candidate(message: str) -> str | None:
    matches = re.findall(r"(?<!\d)(\d{4,7})(?!\d)", str(message or ""))
    return matches[-1] if matches else None


def _build_suggestions(
    draft: TransferDraft,
    missing: list[str],
    beneficiaries: list[dict],
    raw_message: str | None = None,
) -> list[str]:
    suggestions: list[str] = []
    if (
        missing == ["recipient_phone"]
        and draft.amount is not None
        and draft.currency
        and draft.recipient
        and draft.partner_name
        and draft.country_destination
    ):
        suggestions.append(
            (
                f"J'ai compris {draft.amount} {draft.currency} pour {draft.recipient} "
                f"via {draft.partner_name} vers {draft.country_destination}. "
                "Il manque seulement le numero."
            )
        )
    if "recipient_phone" in missing:
        short_phone = _find_short_phone_candidate(raw_message)
        if short_phone:
            suggestions.append(
                f"Le numero {short_phone} est trop court. Utilise un numero complet sur 8 a 15 chiffres."
            )
        suggestions.append("Ajoute le numero du beneficiaire pour l'execution automatique.")
    if "country_destination" in missing:
        suggestions.append("Precise le pays de destination, par exemple Burundi.")
    if "partner_name" in missing:
        suggestions.append("Precise le partenaire, par exemple Lumicash ou Ecocash.")
    if not draft.recognized_beneficiary and beneficiaries:
        sample_names = ", ".join(item["recipient_name"] for item in beneficiaries[:3] if item["recipient_name"])
        if sample_names:
            suggestions.append(f"Beneficiaires habituels reconnus: {sample_names}.")
    return suggestions[:4]


async def process_chat_message(db: AsyncSession, *, user_id, message: str) -> ChatResponse:
    draft = parse_chat_message(message)
    wallet_ctx = await _get_wallet_context(db, user_id)
    beneficiaries = await _get_recent_beneficiaries(db, user_id)
    memories = await _get_recent_chat_memories(db, user_id)

    if not draft.currency:
        draft.currency = wallet_ctx["wallet_currency"]
    draft.wallet_currency = wallet_ctx["wallet_currency"]

    assumptions = []
    assumptions.extend(_learn_from_memories(draft, raw_message=message, memories=memories))
    draft, hist_assumptions = _resolve_beneficiary_from_history(draft, beneficiaries)
    assumptions.extend(hist_assumptions)
    assumptions.extend(_learn_from_history(draft, beneficiaries))
    assumptions.extend(_apply_defaults(draft))

    missing_confirmation = _missing_fields_for_confirmation(draft)
    if missing_confirmation:
        if missing_confirmation == ["recipient"]:
            message_text = (
                "Je reconnais le montant et la devise, mais je n'ai pas pu identifier clairement le beneficiaire."
            )
        else:
            message_text = (
                "Je peux preparer la demande de transfert, mais il me manque encore des informations essentielles."
            )
        return ChatResponse(
            status="NEED_INFO",
            message=message_text,
            data=draft,
            missing_fields=missing_confirmation,
            executable=False,
            suggestions=_build_suggestions(draft, missing_confirmation, beneficiaries, message),
            assumptions=assumptions,
            summary={
                "wallet_currency": wallet_ctx["wallet_currency"],
                "wallet_available": str(wallet_ctx["wallet_available"]),
                "credit_available": str(wallet_ctx["credit_available"]),
            },
        )

    missing_execution = _missing_fields_for_execution(draft)
    executable = (
        not missing_execution
        and str(draft.partner_name or "") in SUPPORTED_TRANSFER_PARTNERS
    )
    partner_text = f" via {draft.partner_name}" if draft.partner_name else ""
    destination_text = f" vers {draft.country_destination}" if draft.country_destination else ""

    return ChatResponse(
        status="CONFIRM",
        message=(
            f"Je suis pret a preparer la demande de transfert de {draft.amount} {draft.currency} "
            f"a {draft.recipient}{partner_text}{destination_text}."
        ),
        data=draft,
        missing_fields=missing_execution if not executable else [],
        executable=executable,
        suggestions=_build_suggestions(draft, missing_execution, beneficiaries, message),
        assumptions=assumptions,
        summary={
            "wallet_currency": wallet_ctx["wallet_currency"],
            "wallet_available": str(wallet_ctx["wallet_available"]),
            "credit_available": str(wallet_ctx["credit_available"]),
            "total_capacity": str(wallet_ctx["total_capacity"]),
        },
    )


def cancel_chat_request() -> ChatResponse:
    return ChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)
