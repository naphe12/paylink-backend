import re
from typing import Any

from app.agent_chat.parser import parse_chat_message
from app.agent_onboarding_chat.parser import parse_agent_onboarding_message
from app.ai.metadata_service import RuntimeMetadata
from app.ai.schemas import ParsedIntent
from app.cash_chat.parser import parse_cash_message
from app.credit_chat.parser import parse_credit_message
from app.escrow_chat.parser import parse_escrow_message
from app.kyc_chat.parser import parse_kyc_message
from app.p2p_chat.parser import parse_p2p_message
from app.services.assistant_semantic_parser import extract_transfer_reference
from app.services.assistant_intent_parser_llm import resolve_intent
from app.transfer_support_chat.parser import parse_transfer_support_message
from app.wallet_chat.parser import parse_wallet_message


AI_INTENTS = {
    "agent_onboarding.guide": "Ask how an agent should perform a field operation or onboarding flow.",
    "agent_onboarding.scenario": "Ask what to do in a specific onboarding scenario or blocker.",
    "cash.deposit": "Prepare a cash deposit request.",
    "cash.withdraw": "Prepare a cash withdrawal request.",
    "cash.capacity": "Ask for available cash capacity before a deposit or withdrawal.",
    "cash.request_status": "Ask for the status of the latest cash deposit or withdrawal request.",
    "wallet.balance": "Ask for current wallet balance or available funds.",
    "wallet.block_reason": "Ask why a wallet action is blocked, frozen, refused or impossible.",
    "wallet.limits": "Ask for daily or monthly wallet limits and usage.",
    "credit.capacity": "Ask how much wallet and credit capacity is currently available.",
    "credit.simulate_capacity": "Ask whether an amount can pass with current wallet and credit capacity.",
    "credit.pending_reason": "Ask why a transfer or credit-related operation is pending or blocked.",
    "escrow.status": "Ask for the status of an escrow order, optionally using an order id.",
    "transfer.status": "Ask for the status of an external transfer, optionally using a reference code.",
    "help.explain_block_reason": "Ask why a transfer is blocked, pending, on hold or waiting review.",
    "transfer.create": "Create or prepare an external transfer to a recipient.",
    "beneficiary.add": "Save or add a beneficiary for a future external transfer.",
    "beneficiary.list": "List known beneficiaries or saved recipients for future transfers.",
    "kyc.status": "Ask for KYC status, level, missing documents or limits.",
    "p2p.trade_status": "Ask for the status or next step of a P2P trade, optionally using a trade id.",
    "p2p.offers_summary": "Ask for a summary of active P2P offers.",
    "unknown": "The request is unclear or unsupported.",
}
SENDER_NAME_PATTERN = re.compile(r"\b(?:de la part de|from)\s+(?P<sender>.+)$", re.IGNORECASE)
BENEFICIARY_ADD_PATTERN = re.compile(
    r"\b(?:ajoute|ajouter|enregistre|enregistrer|sauvegarde|sauvegarder)\b.*\bbeneficiaire\b|\bbeneficiaire\b.*\b(?:ajoute|ajouter|enregistre|enregistrer|sauvegarde|sauvegarder)\b",
    re.IGNORECASE,
)
BENEFICIARY_LIST_PATTERN = re.compile(
    r"\b(?:mes|my)\s+\bbeneficiaires?\b|\bbeneficiaires?\s+\b(?:enregistres|saved|list)\b",
    re.IGNORECASE,
)


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _clean_entity(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _best_synonym_match(message: str, synonyms: dict[str, str]) -> str | None:
    normalized_message = f" {_normalize_text(message)} "
    best_match: tuple[int, str] | None = None
    for synonym, canonical_value in synonyms.items():
        normalized_synonym = _normalize_text(synonym)
        if not normalized_synonym:
            continue
        pattern = rf"(?<!\w){re.escape(normalized_synonym)}(?!\w)"
        if not re.search(pattern, normalized_message):
            continue
        score = len(normalized_synonym)
        if best_match is None or score > best_match[0]:
            best_match = (score, canonical_value)
    return best_match[1] if best_match else None


def _intent_from_synonyms(message: str, metadata: RuntimeMetadata) -> str | None:
    return _best_synonym_match(message, metadata.synonyms.get("intent", {}))


def _network_from_synonyms(message: str, metadata: RuntimeMetadata) -> str | None:
    return _best_synonym_match(message, metadata.synonyms.get("network", {}))


def _intents_with_prompt_hints(metadata: RuntimeMetadata) -> dict[str, str]:
    enriched: dict[str, str] = {}
    for intent_code, description in AI_INTENTS.items():
        fragments = metadata.prompt_fragments.get(intent_code, [])
        hints = [
            str(item.get("content") or "").strip()
            for item in fragments
            if str(item.get("fragment_type") or "").strip() == "feedback_hint"
            and str(item.get("content") or "").strip()
        ]
        if hints:
            enriched[intent_code] = f"{description} Extra guidance: {' | '.join(hints[:3])}"
        else:
            enriched[intent_code] = description
    return enriched


def _build_transfer_entities(message: str, metadata: RuntimeMetadata) -> dict[str, Any]:
    draft = parse_chat_message(message)
    sender_name = None
    sender_match = SENDER_NAME_PATTERN.search(str(message or ""))
    if sender_match:
        sender_name = sender_match.group("sender").strip(" .,:;")
    partner_name = _clean_entity(draft.partner_name) or _network_from_synonyms(message, metadata)
    return {
        "amount": draft.amount,
        "origin_currency": draft.currency,
        "recipient_name": _clean_entity(draft.recipient),
        "partner_name": partner_name,
        "recipient_phone": _clean_entity(draft.recipient_phone),
        "country_destination": _clean_entity(draft.country_destination),
        "sender_name": _clean_entity(sender_name),
    }


def _heuristic_intent(message: str, metadata: RuntimeMetadata) -> tuple[str, dict[str, Any]]:
    cash = parse_cash_message(message)
    if cash.intent == "deposit":
        return "cash.deposit", {
            "amount": cash.amount,
            "currency": cash.currency,
            "note": cash.note,
        }
    if cash.intent == "withdraw":
        return "cash.withdraw", {
            "amount": cash.amount,
            "currency": cash.currency,
            "mobile_number": cash.mobile_number,
            "provider_name": cash.provider_name,
            "note": cash.note,
        }
    if cash.intent == "capacity":
        return "cash.capacity", {}
    if cash.intent == "request_status":
        return "cash.request_status", {}

    wallet_support = parse_transfer_support_message(message)
    wallet_help = parse_wallet_message(message)
    wallet = parse_wallet_message(message)
    if wallet.intent == "balance":
        return "wallet.balance", {}
    if wallet.intent == "limits":
        return "wallet.limits", {}
    if wallet_help.intent in {"account_status"}:
        return "wallet.block_reason", {}

    credit = parse_credit_message(message)
    if credit.intent == "capacity":
        return "credit.capacity", {"currency": credit.currency}
    if credit.intent == "simulate_transfer":
        return "credit.simulate_capacity", {"amount": credit.amount, "currency": credit.currency}
    if credit.intent == "pending_reason":
        return "credit.pending_reason", {}

    kyc = parse_kyc_message(message)
    if kyc.intent in {"status", "missing_docs", "limits", "upgrade_benefits"}:
        return "kyc.status", {"kyc_view": kyc.intent}

    escrow = parse_escrow_message(message)
    if escrow.intent in {"latest_status", "track_order"}:
        return "escrow.status", {"order_id": escrow.order_id}

    p2p = parse_p2p_message(message)
    if p2p.intent in {"latest_trade", "track_trade", "why_blocked", "next_step"}:
        return "p2p.trade_status", {"trade_id": p2p.trade_id, "p2p_view": p2p.intent}
    if p2p.intent == "offers_summary":
        return "p2p.offers_summary", {}

    transfer_support = parse_transfer_support_message(message)
    if transfer_support.intent == "pending_reason":
        return "help.explain_block_reason", {"reference_code": transfer_support.reference_code}
    if transfer_support.intent == "track_transfer":
        return "transfer.status", {"reference_code": transfer_support.reference_code}
    reference_code = extract_transfer_reference(message)
    if reference_code:
        return "transfer.status", {"reference_code": reference_code}

    transfer_entities = _build_transfer_entities(message, metadata)
    if BENEFICIARY_LIST_PATTERN.search(str(message or "")):
        return "beneficiary.list", {}
    if BENEFICIARY_ADD_PATTERN.search(str(message or "")):
        return "beneficiary.add", transfer_entities
    if any(transfer_entities.get(key) is not None for key in ("amount", "recipient_name", "partner_name", "recipient_phone")):
        return "transfer.create", transfer_entities

    onboarding = parse_agent_onboarding_message(message)
    if onboarding.scenario != "none":
        return "agent_onboarding.scenario", {"scenario": onboarding.scenario}
    if onboarding.intent != "unknown":
        return "agent_onboarding.guide", {"guide_topic": onboarding.intent}
    return "unknown", transfer_entities


def _required_missing_fields(intent_code: str, entities: dict[str, Any], metadata: RuntimeMetadata) -> list[str]:
    missing: list[str] = []
    for slot in metadata.slots.get(intent_code, []):
        if not slot.get("required"):
            continue
        slot_name = str(slot.get("slot_name"))
        if entities.get(slot_name) in (None, "", []):
            missing.append(slot_name)
    return missing


def parse_user_message(message: str, metadata: RuntimeMetadata) -> ParsedIntent:
    heuristic_intent, heuristic_entities = _heuristic_intent(message, metadata)
    synonym_intent = _intent_from_synonyms(message, metadata)
    resolved = resolve_intent(
        domain="ai_gateway",
        message=message,
        intents=_intents_with_prompt_hints(metadata),
        heuristic_intent=synonym_intent or heuristic_intent,
    )
    intent_code = resolved.intent or synonym_intent or heuristic_intent or "unknown"
    if intent_code == "unknown" and synonym_intent:
        intent_code = synonym_intent
    if intent_code == "agent_onboarding.guide":
        entities = {
            "guide_topic": heuristic_entities.get("guide_topic"),
        }
    elif intent_code == "agent_onboarding.scenario":
        entities = {
            "scenario": heuristic_entities.get("scenario"),
        }
    elif intent_code in {"cash.capacity", "cash.request_status", "wallet.block_reason"}:
        entities = {}
    elif intent_code in {"cash.deposit", "cash.withdraw"}:
        entities = heuristic_entities
    elif intent_code == "transfer.create":
        entities = heuristic_entities
    elif intent_code == "beneficiary.add":
        entities = heuristic_entities
    elif intent_code == "beneficiary.list":
        entities = {}
    elif intent_code == "credit.capacity":
        entities = {
            "currency": heuristic_entities.get("currency"),
        }
    elif intent_code == "credit.simulate_capacity":
        entities = {
            "amount": heuristic_entities.get("amount"),
            "currency": heuristic_entities.get("currency"),
        }
    elif intent_code == "credit.pending_reason":
        entities = {}
    elif intent_code == "wallet.limits":
        entities = {}
    elif intent_code == "escrow.status":
        entities = {
            "order_id": heuristic_entities.get("order_id"),
        }
    elif intent_code == "kyc.status":
        entities = {
            "kyc_view": heuristic_entities.get("kyc_view"),
        }
    elif intent_code == "p2p.trade_status":
        entities = {
            "trade_id": heuristic_entities.get("trade_id"),
            "p2p_view": heuristic_entities.get("p2p_view"),
        }
    elif intent_code == "p2p.offers_summary":
        entities = {}
    elif intent_code == "transfer.status":
        entities = {
            "reference_code": heuristic_entities.get("reference_code"),
        }
    else:
        entities = {}
    missing_fields = _required_missing_fields(intent_code, entities, metadata)
    requires_confirmation = bool(metadata.intents.get(intent_code, {}).get("requires_confirmation", False))
    return ParsedIntent(
        intent=intent_code,
        confidence=resolved.confidence,
        entities=entities,
        missing_fields=missing_fields,
        requires_confirmation=requires_confirmation,
    )
