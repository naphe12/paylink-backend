import unicodedata

from app.agent_onboarding_chat.schemas import AgentOnboardingDraft


def normalize_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _detect_intent(message: str) -> str:
    normalized = normalize_text(message)
    if "cash in" in normalized or "cash-in" in normalized or "depot" in normalized or "cashin" in normalized:
        return "cash_in"
    if "cash out" in normalized or "cash-out" in normalized or "retrait" in normalized or "cashout" in normalized:
        return "cash_out"
    if "scan" in normalized or "qr" in normalized:
        return "scan_client"
    if "transfert externe" in normalized or "external transfer" in normalized or "partenaire" in normalized:
        return "external_transfer"
    if "verifier" in normalized or "verification" in normalized or "kyc" in normalized or "client" in normalized:
        return "client_checks"
    if "erreur" in normalized or "probleme" in normalized or "blocage" in normalized:
        return "common_errors"
    return "unknown"


def _detect_scenario(message: str) -> str:
    normalized = normalize_text(message)
    if "nouveau client" in normalized or "premier client" in normalized or "nouvelle cliente" in normalized:
        return "new_client"
    if (
        "sans kyc" in normalized
        or "kyc manque" in normalized
        or "kyc manquant" in normalized
        or "kyc non verifie" in normalized
        or "client non verifie" in normalized
    ):
        return "missing_kyc"
    if (
        "cash out bloque" in normalized
        or "cash-out bloque" in normalized
        or "retrait bloque" in normalized
        or "cash out refuse" in normalized
        or "cash-out refuse" in normalized
    ):
        return "blocked_cash_out"
    return "none"


def parse_agent_onboarding_message(message: str) -> AgentOnboardingDraft:
    text = str(message or "").strip()
    return AgentOnboardingDraft(intent=_detect_intent(text), scenario=_detect_scenario(text), raw_message=text)
