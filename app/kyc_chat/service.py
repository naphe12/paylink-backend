from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.ai.legacy_adapters import handle_kyc_chat_with_ai
from app.kyc_chat.parser import parse_kyc_message
from app.kyc_chat.schemas import KycChatResponse, KycDraft
from app.models.kyc_verifications import KycVerifications
from app.models.users import Users


TIER_LIMITS = {
    0: {"daily_limit": 30000, "monthly_limit": 30000},
    1: {"daily_limit": 1_000_000, "monthly_limit": 5_000_000},
    2: {"daily_limit": 10_000_000, "monthly_limit": 30_000_000},
    3: {"daily_limit": 999_999_999, "monthly_limit": 999_999_999},
}


async def _get_user_context(db: AsyncSession, user_id) -> tuple[Users | None, KycVerifications | None]:
    verification = None
    try:
        verification = await db.scalar(
            select(KycVerifications)
            .where(KycVerifications.user_id == user_id)
            .order_by(KycVerifications.created_at.desc())
        )
    except ProgrammingError as exc:
        # Some deployments do not have the optional paylink.kyc_verifications table yet.
        if "kyc_verifications" not in str(getattr(exc, "orig", exc)).lower():
            raise
        await db.rollback()
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    return user, verification


def _format_doc_label(doc_name: str) -> str:
    mapping = {
        "id_front": "piece d'identite recto",
        "id_back": "piece d'identite verso",
        "selfie_liveness": "selfie de verification",
        "proof_of_address": "justificatif d'adresse",
        "source_of_funds": "justificatif de provenance des fonds",
    }
    return mapping.get(str(doc_name or "").strip(), str(doc_name or "").replace("_", " ").strip() or "document")


def _build_suggestions(draft: KycDraft) -> list[str]:
    if draft.intent == "unknown":
        return [
            "Demande ton niveau KYC actuel.",
            "Demande quels documents manquent.",
            "Demande les limites journalieres et mensuelles.",
            "Demande ce que debloque le niveau suivant.",
            "Demande pourquoi ton dossier KYC est bloque.",
            "Demande le statut exact de verification.",
        ]
    return []


def _build_summary(user: Users | None, verification: KycVerifications | None, missing_docs: list[str]) -> dict:
    return {
        "kyc_status": str(getattr(user, "kyc_status", "") or "unknown"),
        "kyc_tier": int(getattr(user, "kyc_tier", 0) or 0),
        "daily_limit": str(getattr(user, "daily_limit", 0) or 0),
        "monthly_limit": str(getattr(user, "monthly_limit", 0) or 0),
        "used_daily": str(getattr(user, "used_daily", 0) or 0),
        "used_monthly": str(getattr(user, "used_monthly", 0) or 0),
        "verification_status": str(getattr(verification, "status", "") or ""),
        "verification_tier": str(getattr(verification, "tier", "") or ""),
        "missing_docs": missing_docs,
    }


def _resolve_missing_docs(user: Users | None, verification: KycVerifications | None) -> list[str]:
    if verification:
        required_docs = list(getattr(verification, "required_docs", []) or [])
        collected_docs = set(getattr(verification, "collected_docs", []) or [])
        missing = [doc for doc in required_docs if doc not in collected_docs]
        if missing:
            return missing

    inferred_missing: list[str] = []
    if not getattr(user, "kyc_document_front_url", None):
        inferred_missing.append("id_front")
    if not getattr(user, "selfie_url", None):
        inferred_missing.append("selfie_liveness")
    return inferred_missing


def _next_tier_message(current_tier: int) -> str:
    next_tier = min(current_tier + 1, 3)
    current_limits = TIER_LIMITS.get(current_tier, TIER_LIMITS[0])
    next_limits = TIER_LIMITS.get(next_tier, TIER_LIMITS[3])
    if next_tier == current_tier:
        return "Tu es deja au niveau KYC le plus eleve configure actuellement."
    return (
        f"Le niveau suivant est {next_tier}. "
        f"Il ferait passer la limite journaliere de {current_limits['daily_limit']} a {next_limits['daily_limit']} "
        f"et la limite mensuelle de {current_limits['monthly_limit']} a {next_limits['monthly_limit']}."
    )


async def process_kyc_message(db: AsyncSession, *, user_id, message: str) -> KycChatResponse:
    user_for_ai = await db.scalar(select(Users).where(Users.user_id == user_id))
    if user_for_ai is not None:
        ai_response, used_ai = await handle_kyc_chat_with_ai(
            db,
            current_user=user_for_ai,
            message=message,
        )
        if used_ai:
            return ai_response

    draft = parse_kyc_message(message)
    user, verification = await _get_user_context(db, user_id)
    if not user:
        return KycChatResponse(
            status="ERROR",
            message="Utilisateur introuvable pour analyser la situation KYC.",
            data=draft,
        )

    missing_docs = _resolve_missing_docs(user, verification)
    summary = _build_summary(user, verification, missing_docs)
    kyc_status = str(getattr(user, "kyc_status", "") or "unknown")
    kyc_tier = int(getattr(user, "kyc_tier", 0) or 0)

    if draft.intent == "status":
        message_text = (
            f"Statut KYC actuel: {kyc_status}. Niveau: {kyc_tier}. "
            f"Limites actuelles: {getattr(user, 'daily_limit', 0)} par jour et {getattr(user, 'monthly_limit', 0)} par mois."
        )
        assumptions = []
        if kyc_status == "rejected" and getattr(user, "kyc_reject_reason", None):
            assumptions.append(f"Motif du rejet connu: {user.kyc_reject_reason}.")
        elif kyc_status in {"unverified", "reviewing", "pending"} and missing_docs:
            assumptions.append(
                "Documents encore attendus: " + ", ".join(_format_doc_label(item) for item in missing_docs) + "."
            )
        return KycChatResponse(
            status="INFO",
            message=message_text,
            data=draft,
            assumptions=assumptions,
            summary=summary,
        )

    if draft.intent == "missing_docs":
        if missing_docs:
            return KycChatResponse(
                status="INFO",
                message="Documents encore attendus: " + ", ".join(_format_doc_label(item) for item in missing_docs) + ".",
                data=draft,
                assumptions=[
                    "Tu peux les soumettre depuis la page KYC de ton compte.",
                ],
                summary=summary,
            )
        return KycChatResponse(
            status="INFO",
            message="Je ne vois pas de document KYC manquant dans les donnees disponibles.",
            data=draft,
            assumptions=["Si ton dossier est encore bloque, il peut etre en revue manuelle."],
            summary=summary,
        )

    if draft.intent == "limits":
        return KycChatResponse(
            status="INFO",
            message=(
                f"Tes plafonds actuels sont {getattr(user, 'daily_limit', 0)} par jour et "
                f"{getattr(user, 'monthly_limit', 0)} par mois. "
                f"Utilisation en cours: {getattr(user, 'used_daily', 0)} aujourd'hui et {getattr(user, 'used_monthly', 0)} ce mois."
            ),
            data=draft,
            summary=summary,
        )

    if draft.intent == "upgrade_benefits":
        return KycChatResponse(
            status="INFO",
            message=_next_tier_message(kyc_tier),
            data=draft,
            assumptions=["L'augmentation effective depend de la validation du dossier KYC."],
            summary=summary,
        )

    return KycChatResponse(
        status="NEED_INFO",
        message="Je peux t'aider sur le statut KYC, les documents manquants, les limites ou ce que debloque le niveau suivant.",
        data=draft,
        suggestions=_build_suggestions(draft),
        summary=summary,
    )


def cancel_kyc_request() -> KycChatResponse:
    return KycChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)
