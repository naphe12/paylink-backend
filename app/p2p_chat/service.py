from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.legacy_adapters import handle_p2p_chat_with_ai
from app.models.p2p_dispute import P2PDispute
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory
from app.services.assistant_suggestions import build_assistant_suggestions
from app.p2p_chat.parser import parse_p2p_message
from app.p2p_chat.schemas import P2PChatResponse


def _build_suggestions() -> list[str]:
    return build_assistant_suggestions("p2p")


def _status_text(value) -> str:
    return str(getattr(value, "value", value) or "").upper()


def _next_step_for_status(status: str) -> str:
    if status == "CREATED":
        return "Le trade vient d'etre cree. Attendez l'allocation escrow ou l'etape crypto."
    if status == "AWAITING_CRYPTO":
        return "Le vendeur doit encore verrouiller ou envoyer la crypto dans l'escrow."
    if status == "CRYPTO_LOCKED":
        return "La crypto est verrouillee. L'acheteur peut maintenant envoyer le paiement fiat."
    if status == "AWAITING_FIAT":
        return "Le trade attend le paiement fiat de l'acheteur."
    if status == "FIAT_SENT":
        return "Le vendeur doit verifier puis confirmer la reception du fiat."
    if status == "FIAT_CONFIRMED":
        return "La confirmation fiat est faite. Le trade va vers la liberation."
    if status == "RELEASED":
        return "Le trade est termine."
    if status == "DISPUTED":
        return "Le trade est en litige et attend une resolution."
    if status in {"CANCELLED", "EXPIRED", "RESOLVED"}:
        return "Verifier l'issue du trade et ouvrir la room si vous avez besoin du detail."
    return "Verifier la timeline du trade pour connaitre l'etape suivante."


def _blocked_reasons(status: str, dispute, last_history) -> list[str]:
    reasons: list[str] = []
    if status in {"CREATED", "AWAITING_CRYPTO"}:
        reasons.append("La crypto n'est pas encore verrouillee dans l'escrow.")
    if status in {"CRYPTO_LOCKED", "AWAITING_FIAT"}:
        reasons.append("Le trade attend encore le paiement fiat de l'acheteur.")
    if status == "FIAT_SENT":
        reasons.append("Le vendeur n'a pas encore confirme la reception du fiat.")
    if status == "DISPUTED":
        reasons.append("Un litige est ouvert sur ce trade.")
    if dispute:
        reasons.append(f"Litige actuel: {_status_text(getattr(dispute, 'status', 'OPEN'))}.")
    if last_history and getattr(last_history, "note", None):
        reasons.append(f"Derniere note: {last_history.note}")
    if not reasons:
        reasons.append("Le trade suit encore son flux normal.")
    return reasons


def _serialize_trade_summary(trade, dispute, open_offers_count: int) -> dict:
    status = _status_text(getattr(trade, "status", ""))
    return {
        "trade_id": str(getattr(trade, "trade_id", "") or ""),
        "status": status,
        "token_amount": str(getattr(trade, "token_amount", "") or ""),
        "token": str(_status_text(getattr(trade, "token", ""))),
        "bif_amount": str(getattr(trade, "bif_amount", "") or ""),
        "payment_method": _status_text(getattr(trade, "payment_method", "")),
        "created_at": getattr(trade, "created_at", None),
        "dispute_status": _status_text(getattr(dispute, "status", "")) if dispute else "",
        "open_offers_count": open_offers_count,
        "next_step": _next_step_for_status(status),
    }


async def _load_trade_context(db: AsyncSession, *, user_id, trade_id: str | None):
    if trade_id:
        trade = await db.scalar(
            select(P2PTrade).where(
                P2PTrade.trade_id == trade_id,
                or_(P2PTrade.buyer_id == user_id, P2PTrade.seller_id == user_id),
            )
        )
    else:
        trade = await db.scalar(
            select(P2PTrade)
            .where(or_(P2PTrade.buyer_id == user_id, P2PTrade.seller_id == user_id))
            .order_by(desc(P2PTrade.created_at))
        )
    dispute = None
    last_history = None
    if trade:
        dispute = await db.scalar(
            select(P2PDispute).where(P2PDispute.trade_id == trade.trade_id).order_by(desc(P2PDispute.created_at))
        )
        last_history = await db.scalar(
            select(P2PTradeStatusHistory)
            .where(P2PTradeStatusHistory.trade_id == trade.trade_id)
            .order_by(desc(P2PTradeStatusHistory.created_at))
        )
    open_offers = await db.execute(
        select(P2POffer).where(P2POffer.user_id == user_id, P2POffer.is_active.is_(True)).order_by(desc(P2POffer.created_at))
    )
    offers = list(open_offers.scalars().all())
    return trade, dispute, last_history, offers


async def process_p2p_message(db: AsyncSession, *, user_id, message: str) -> P2PChatResponse:
    from app.models.users import Users

    user_for_ai = await db.scalar(select(Users).where(Users.user_id == user_id))
    if user_for_ai is not None:
        ai_response, used_ai = await handle_p2p_chat_with_ai(
            db,
            current_user=user_for_ai,
            message=message,
        )
        if used_ai:
            return ai_response

    draft = parse_p2p_message(message)
    trade, dispute, last_history, offers = await _load_trade_context(db, user_id=user_id, trade_id=draft.trade_id)

    if draft.intent == "unknown":
        return P2PChatResponse(
            status="NEED_INFO",
            message="Je peux suivre un trade P2P, expliquer un blocage ou resumer vos offres.",
            data=draft,
            suggestions=_build_suggestions(),
        )

    if draft.intent == "offers_summary":
        if not offers:
            return P2PChatResponse(
                status="INFO",
                message="Je ne vois pas d'offre P2P active pour le moment.",
                data=draft,
                suggestions=_build_suggestions(),
                summary={"open_offers_count": 0},
            )
        latest_offer = offers[0]
        summary = {
            "open_offers_count": len(offers),
            "latest_offer_side": _status_text(getattr(latest_offer, "side", "")),
            "latest_offer_token": _status_text(getattr(latest_offer, "token", "")),
            "latest_offer_available": str(getattr(latest_offer, "available_amount", "") or ""),
            "latest_offer_payment_method": _status_text(getattr(latest_offer, "payment_method", "")),
        }
        return P2PChatResponse(
            status="INFO",
            message=f"Vous avez actuellement {len(offers)} offre(s) P2P active(s).",
            data=draft,
            assumptions=["La derniere offre active est reprise dans le resume ci-contre."],
            summary=summary,
        )

    if not trade:
        return P2PChatResponse(
            status="INFO",
            message="Je ne trouve pas de trade P2P correspondant a cette demande.",
            data=draft,
            suggestions=_build_suggestions(),
        )

    summary = _serialize_trade_summary(trade, dispute, len(offers))
    if draft.intent in {"latest_trade", "track_trade"}:
        return P2PChatResponse(
            status="INFO",
            message=f"Votre trade P2P est actuellement au statut {summary['status']}.",
            data=draft,
            assumptions=[summary["next_step"]],
            summary=summary,
        )

    if draft.intent == "why_blocked":
        return P2PChatResponse(
            status="INFO",
            message=f"Le trade est au statut {summary['status']}. Voici les causes probables du blocage ou de l'attente.",
            data=draft,
            assumptions=_blocked_reasons(summary["status"], dispute, last_history),
            summary=summary,
        )

    if draft.intent == "next_step":
        return P2PChatResponse(
            status="INFO",
            message=summary["next_step"],
            data=draft,
            assumptions=_blocked_reasons(summary["status"], dispute, last_history),
            summary=summary,
        )

    return P2PChatResponse(
        status="NEED_INFO",
        message="Je peux suivre un trade P2P et expliquer l'etape en cours.",
        data=draft,
        suggestions=_build_suggestions(),
    )


def cancel_p2p_request() -> P2PChatResponse:
    return P2PChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)
