from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.legacy_adapters import handle_transfer_support_with_ai
from app.models.credit_lines import CreditLines
from app.models.external_transfers import ExternalTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.assistant_suggestions import build_assistant_suggestions
from app.services.external_transfer_capacity import effective_external_transfer_capacity
from app.transfer_support_chat.parser import parse_transfer_support_message
from app.transfer_support_chat.schemas import TransferSupportChatResponse


STATUS_LABELS = {
    "initiated": "demande recue",
    "pending": "en attente de validation",
    "approved": "validee et en attente d'execution",
    "completed": "terminee",
    "succeeded": "terminee avec succes",
    "failed": "echouee",
    "cancelled": "annulee",
    "reversed": "annulee ou retournee",
}
AML_ALERT_THRESHOLD = 50
AML_MANUAL_REVIEW_THRESHOLD = 60
AML_AUTO_FREEZE_THRESHOLD = 80
AML_REASON_LABELS = {
    "AML_KYC_UNVERIFIED": "niveau KYC non verifie",
    "AML_KYC_BASIC": "niveau KYC basique",
    "AML_NEW_ACCOUNT_LT_7D": "compte tres recent",
    "AML_NEW_ACCOUNT_LT_30D": "compte recent",
    "AML_AMOUNT_GE_1000000": "montant tres eleve",
    "AML_AMOUNT_GE_300000": "montant eleve",
    "AML_EXTERNAL_CHANNEL": "canal transfert externe",
    "AML_SCORE_ALERT": "alerte AML",
    "AML_SCORE_MANUAL_REVIEW": "revue manuelle AML",
    "AML_SCORE_CRITICAL": "score AML critique",
}


def _fmt_decimal(value: Decimal) -> str:
    return format(Decimal(value).normalize(), "f").rstrip("0").rstrip(".") if Decimal(value) != 0 else "0"


def _build_suggestions() -> list[str]:
    return build_assistant_suggestions("transfer_support")


def _describe_aml_reason(metadata: dict) -> str:
    aml_score = metadata.get("aml_risk_score")
    manual_review = bool(metadata.get("aml_manual_review_required"))
    if aml_score is None:
        return "un controle AML manuel est en cours"
    try:
        score = int(aml_score)
    except Exception:
        return f"un controle AML manuel est en cours (score enregistre: {aml_score})"

    if score >= AML_AUTO_FREEZE_THRESHOLD:
        return f"le score AML est critique ({score}) et demande une intervention conformite prioritaire"
    if score >= AML_MANUAL_REVIEW_THRESHOLD:
        return f"le score AML ({score}) depasse le seuil de revue manuelle ({AML_MANUAL_REVIEW_THRESHOLD})"
    if manual_review or score >= AML_ALERT_THRESHOLD:
        return f"le score AML ({score}) a declenche une alerte de conformite (seuil {AML_ALERT_THRESHOLD})"
    return f"une verification AML reste attachee au dossier (score {score})"


def _describe_aml_reason_codes(metadata: dict) -> str | None:
    reason_codes = [str(item) for item in (metadata.get("aml_reason_codes") or [])]
    labels = [AML_REASON_LABELS.get(code) for code in reason_codes if AML_REASON_LABELS.get(code)]
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} et {labels[1]}"
    return f"{', '.join(labels[:-1])} et {labels[-1]}"


async def _find_transfer(db: AsyncSession, *, user_id, reference_code: str | None):
    if reference_code:
        return await db.scalar(
            select(ExternalTransfers)
            .where(
                ExternalTransfers.user_id == user_id,
                ExternalTransfers.reference_code == reference_code,
            )
            .order_by(desc(ExternalTransfers.created_at))
        )
    return await db.scalar(
        select(ExternalTransfers)
        .where(ExternalTransfers.user_id == user_id)
        .order_by(desc(ExternalTransfers.created_at))
    )


async def _find_linked_transaction(db: AsyncSession, transfer_id):
    return await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer_id)
    )


async def _get_wallet_context(db: AsyncSession, user_id) -> dict:
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(desc(CreditLines.created_at))
    )
    wallet_currency = str(getattr(wallet, "currency_code", "") or "").upper() or "EUR"
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
        "total_capacity": effective_external_transfer_capacity(wallet_available, credit_available),
    }


def _status_message(status: str, *, review_reasons: list[str], metadata: dict, tx_status: str | None) -> tuple[str, list[str]]:
    normalized_status = str(status or "").lower()
    human_status = STATUS_LABELS.get(normalized_status, normalized_status or "inconnu")
    assumptions: list[str] = []

    if normalized_status in {"pending", "initiated"}:
        if "insufficient_funds" in review_reasons and "aml" in review_reasons:
            shortfall = str(metadata.get("required_credit_topup") or "").strip()
            funding_part = (
                f"une couverture complementaire de {shortfall}" if shortfall else "une couverture de fonds"
            )
            message = f"La demande est en pending parce qu'elle attend a la fois {funding_part} et {_describe_aml_reason(metadata)}."
        elif "insufficient_funds" in review_reasons:
            shortfall = str(metadata.get("required_credit_topup") or "").strip()
            if shortfall:
                message = f"La demande est en pending parce qu'il manque encore {shortfall} pour la financer."
            else:
                message = "La demande est en pending parce que la couverture disponible etait insuffisante au moment de la creation."
        elif "aml" in review_reasons or metadata.get("aml_manual_review_required"):
            message = f"La demande est en pending parce que {_describe_aml_reason(metadata)}."
            detail = _describe_aml_reason_codes(metadata)
            if detail:
                message = f"{message} Signaux principaux: {detail}."
        elif metadata.get("funding_pending"):
            shortfall = str(metadata.get("required_credit_topup") or "").strip()
            if shortfall:
                message = f"La demande est en pending parce qu'un financement complementaire de {shortfall} est encore attendu avant validation."
            else:
                message = "La demande est en pending parce qu'un financement complementaire est encore attendu avant validation."
        else:
            message = "La demande est en pending et attend encore une validation manuelle."
    elif normalized_status == "approved":
        message = "La demande est approved: elle a ete validee et attend maintenant l'execution finale par l'agent ou le partenaire."
    elif normalized_status in {"completed", "succeeded"}:
        message = "La demande est terminee avec succes."
    elif normalized_status == "failed":
        message = "La demande a echoue. Il faut verifier les details de traitement ou reprendre l'operation."
    elif normalized_status == "cancelled":
        message = "La demande a ete annulee."
    else:
        message = f"Le statut actuel est {human_status}."

    if tx_status:
        assumptions.append(f"Statut de transaction liee: {tx_status}.")
    processed_by = metadata.get("processed_by_user_id") or metadata.get("processed_by_agent")
    if processed_by:
        assumptions.append("Une intervention agent ou backoffice a deja ete enregistree sur cette demande.")
    if metadata.get("funding_pending"):
        assumptions.append("Le dossier comporte un financement en attente.")
    if metadata.get("aml_risk_score") is not None:
        assumptions.append(
            f"Score AML enregistre: {metadata.get('aml_risk_score')} "
            f"(alerte {AML_ALERT_THRESHOLD}, revue manuelle externe {AML_MANUAL_REVIEW_THRESHOLD})."
        )
    aml_reason_detail = _describe_aml_reason_codes(metadata)
    if aml_reason_detail:
        assumptions.append(f"Motifs AML enregistres: {aml_reason_detail}.")
    return message, assumptions


async def process_transfer_support_message(db: AsyncSession, *, user_id, message: str) -> TransferSupportChatResponse:
    user_for_ai = await db.scalar(select(Users).where(Users.user_id == user_id))
    if user_for_ai is not None:
        ai_response, used_ai = await handle_transfer_support_with_ai(
            db,
            current_user=user_for_ai,
            message=message,
        )
        if used_ai:
            return ai_response

    draft = parse_transfer_support_message(message)
    transfer = await _find_transfer(db, user_id=user_id, reference_code=draft.reference_code)
    user = user_for_ai
    wallet_ctx = await _get_wallet_context(db, user_id)

    if draft.intent == "capacity":
        return TransferSupportChatResponse(
            status="INFO",
            message=(
                f"Capacite financiere actuelle: **wallet {_fmt_decimal(wallet_ctx['wallet_available'])} {wallet_ctx['wallet_currency']}**, "
                f"**credit disponible {_fmt_decimal(wallet_ctx['credit_available'])} {wallet_ctx['wallet_currency']}**, "
                f"soit **{_fmt_decimal(wallet_ctx['total_capacity'])} {wallet_ctx['wallet_currency']} utilisables**."
            ),
            data=draft,
            assumptions=[
                "Regle appliquee: capacite financiere = solde wallet + ligne de credit disponible active.",
            ],
            summary={
                "user_id": str(getattr(user, "user_id", "") or "") or None,
                "user_name": str(getattr(user, "full_name", "") or "") or None,
                "user_email": str(getattr(user, "email", "") or "") or None,
                "user_phone": str(getattr(user, "phone_e164", "") or "") or None,
                "wallet_currency": wallet_ctx["wallet_currency"],
                "wallet_available": _fmt_decimal(wallet_ctx["wallet_available"]),
                "credit_available": _fmt_decimal(wallet_ctx["credit_available"]),
                "total_capacity": _fmt_decimal(wallet_ctx["total_capacity"]),
            },
            suggestions=[
                "Exemple: wallet 10 EUR + credit disponible 50 EUR = capacite 60 EUR.",
                "Tu peux aussi demander pourquoi une demande est pending.",
            ],
        )

    if draft.intent == "unknown":
        return TransferSupportChatResponse(
            status="NEED_INFO",
            message="Je peux suivre une demande de transfert, expliquer pourquoi elle est pending, ou donner la capacite financiere actuelle.",
            data=draft,
            suggestions=_build_suggestions(),
        )

    if not transfer:
        return TransferSupportChatResponse(
            status="INFO",
            message=(
                f"Je ne trouve aucune demande avec la reference {draft.reference_code}."
                if draft.reference_code
                else "Je ne trouve pas encore de demande de transfert pour ce compte."
            ),
            data=draft,
            suggestions=_build_suggestions(),
        )

    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    review_reasons = list(metadata.get("review_reasons") or [])
    linked_tx = await _find_linked_transaction(db, transfer.transfer_id)
    tx_status = str(getattr(linked_tx, "status", "") or "").lower() or None
    status_text, assumptions = _status_message(
        str(getattr(transfer, "status", "") or ""),
        review_reasons=review_reasons,
        metadata=metadata,
        tx_status=tx_status,
    )

    summary = {
        "user_id": str(getattr(user, "user_id", "") or "") or None,
        "user_name": str(getattr(user, "full_name", "") or "") or None,
        "user_email": str(getattr(user, "email", "") or "") or None,
        "user_phone": str(getattr(user, "phone_e164", "") or "") or None,
        "transfer_id": str(getattr(transfer, "transfer_id", "") or "") or None,
        "transaction_id": str(getattr(linked_tx, "tx_id", "") or "") or None,
        "reference_code": transfer.reference_code,
        "transfer_status": str(getattr(transfer, "status", "") or ""),
        "transaction_status": tx_status,
        "recipient_name": transfer.recipient_name,
        "recipient_phone": str(getattr(transfer, "recipient_phone", "") or "") or None,
        "partner_name": transfer.partner_name,
        "country_destination": transfer.country_destination,
        "amount": str(getattr(transfer, "amount", "") or ""),
        "currency": str(getattr(transfer, "currency", "") or ""),
        "created_at": transfer.created_at.isoformat() if getattr(transfer, "created_at", None) else None,
        "processed_at": getattr(transfer, "processed_at", None).isoformat() if getattr(transfer, "processed_at", None) else None,
        "review_reasons": review_reasons,
        "funding_pending": bool(metadata.get("funding_pending")),
        "next_step": (
            "Attendre validation manuelle ou couverture."
            if str(getattr(transfer, "status", "") or "").lower() in {"pending", "initiated"}
            else "Attendre execution finale."
            if str(getattr(transfer, "status", "") or "").lower() == "approved"
            else "Aucune action immediate."
        ),
    }

    if draft.intent == "status_help":
        response_message = (
            "Statuts principaux: pending = revue ou financement en attente, approved = valide mais pas encore execute, "
            "succeeded/completed = termine, failed = echec."
        )
    else:
        response_message = status_text

    return TransferSupportChatResponse(
        status="INFO",
        message=response_message,
        data=draft,
        assumptions=assumptions,
        summary=summary,
    )


def cancel_transfer_support_request() -> TransferSupportChatResponse:
    return TransferSupportChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)
