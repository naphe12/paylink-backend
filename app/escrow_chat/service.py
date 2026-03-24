from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.escrow_chat.parser import parse_escrow_message
from app.escrow_chat.schemas import EscrowChatResponse
from app.models.escrow_order import EscrowOrder


def _build_suggestions() -> list[str]:
    return [
        "Quel est le statut de mon dernier escrow ?",
        "Pourquoi mon escrow est en attente ?",
        "Quelle est la prochaine etape de mon escrow ?",
        "Suis la commande 00000000-0000-0000-0000-000000000000",
    ]


def _status_text(order) -> str:
    return str(getattr(getattr(order, "status", None), "value", getattr(order, "status", "")) or "").upper()


def _next_step_for_status(status: str) -> str:
    if status == "CREATED":
        return "Envoyer le depot USDC vers l'adresse escrow puis attendre la detection."
    if status == "FUNDED":
        return "Le depot est detecte. La prochaine etape est la conversion ou le swap."
    if status == "SWAPPED":
        return "Le swap est termine. La prochaine etape est la preparation du payout."
    if status == "PAYOUT_PENDING":
        return "Le payout fiat est en preparation ou en validation avant paiement final."
    if status == "PAID_OUT":
        return "L'ordre est termine. Verifie simplement la bonne reception du payout."
    if status in {"FAILED", "CANCELLED", "EXPIRED"}:
        return "Verifier la raison de l'echec ou relancer une nouvelle commande si necessaire."
    if status in {"REFUND_PENDING", "REFUNDED"}:
        return "Le dossier est oriente vers un remboursement ou deja rembourse."
    return "Verifier le detail de la commande pour connaitre l'etape suivante."


def _pending_reasons(order, status: str) -> list[str]:
    reasons: list[str] = []
    if status == "CREATED":
        reasons.append("Le depot USDC n'a pas encore ete detecte ou confirme.")
    if status == "FUNDED":
        reasons.append("Le depot est recu mais la conversion n'est pas encore finalisee.")
    if status == "SWAPPED":
        reasons.append("Le swap est termine mais le payout fiat n'a pas encore ete prepare.")
    if status == "PAYOUT_PENDING":
        reasons.append("Le payout est en cours de traitement ou de verification operateur.")
    flags = list(getattr(order, "flags", []) or [])
    if flags:
        reasons.append(f"Flags detectes: {', '.join(str(flag) for flag in flags)}.")
    if not reasons:
        reasons.append("Le dossier est en cours de traitement dans le flux escrow.")
    return reasons


def _serialize_summary(order) -> dict:
    status = _status_text(order)
    return {
        "order_id": str(getattr(order, "id", "") or ""),
        "status": status,
        "created_at": getattr(order, "created_at", None),
        "network": str(getattr(getattr(order, "deposit_network", None), "value", getattr(order, "deposit_network", "")) or ""),
        "deposit_address": str(getattr(order, "deposit_address", "") or ""),
        "usdc_expected": str(getattr(order, "usdc_expected", "") or ""),
        "bif_target": str(getattr(order, "bif_target", "") or ""),
        "payout_provider": str(getattr(order, "payout_provider", "") or ""),
        "payout_account": str(getattr(order, "payout_account_number", "") or ""),
        "next_step": _next_step_for_status(status),
    }


async def _load_order(db: AsyncSession, *, user_id, order_id: str | None):
    if order_id:
        return await db.scalar(
            select(EscrowOrder).where(EscrowOrder.user_id == user_id, EscrowOrder.id == order_id)
        )
    return await db.scalar(
        select(EscrowOrder).where(EscrowOrder.user_id == user_id).order_by(desc(EscrowOrder.created_at))
    )


async def process_escrow_message(db: AsyncSession, *, user_id, message: str) -> EscrowChatResponse:
    draft = parse_escrow_message(message)
    order = await _load_order(db, user_id=user_id, order_id=draft.order_id)

    if draft.intent == "unknown":
        return EscrowChatResponse(
            status="NEED_INFO",
            message="Je peux suivre une commande escrow, expliquer son statut et la prochaine etape.",
            data=draft,
            suggestions=_build_suggestions(),
        )

    if not order:
        return EscrowChatResponse(
            status="INFO",
            message="Je ne trouve pas de commande escrow correspondant a cette demande.",
            data=draft,
            suggestions=_build_suggestions(),
        )

    status = _status_text(order)
    summary = _serialize_summary(order)

    if draft.intent in {"latest_status", "track_order"}:
        return EscrowChatResponse(
            status="INFO",
            message=f"Votre commande escrow est actuellement au statut {status}.",
            data=draft,
            assumptions=[summary["next_step"]],
            summary=summary,
        )

    if draft.intent == "why_pending":
        return EscrowChatResponse(
            status="INFO",
            message=f"Le statut actuel est {status}. Voici ce qui explique probablement l'attente.",
            data=draft,
            assumptions=_pending_reasons(order, status),
            summary=summary,
        )

    if draft.intent == "next_step":
        return EscrowChatResponse(
            status="INFO",
            message=summary["next_step"],
            data=draft,
            assumptions=_pending_reasons(order, status),
            summary=summary,
        )

    return EscrowChatResponse(
        status="NEED_INFO",
        message="Je peux suivre une commande escrow et expliquer l'etape en cours.",
        data=draft,
        suggestions=_build_suggestions(),
    )


def cancel_escrow_request() -> EscrowChatResponse:
    return EscrowChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)
