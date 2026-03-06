from __future__ import annotations

from datetime import timedelta
from functools import partial
from urllib.parse import quote_plus

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as core_settings
from app.core.security import create_access_token
from app.models.users import Users
from app.services.mailjet_service import MailjetEmailService


def _build_agent_confirm_link(trade_id: str, token: str) -> str:
    backend_base = str(getattr(core_settings, "BACKEND_URL", "") or "").strip()
    base = (backend_base or str(getattr(core_settings, "FRONTEND_URL", "http://localhost:5173") or "http://localhost:5173")).rstrip("/")
    return f"{base}/api/p2p/trades/{trade_id}/fiat-sent-by-agent?token={quote_plus(token)}"


def _build_email_html(*, trade_id: str, amount_bif: str, confirm_link: str) -> str:
    return f"""
    <h2>Action requise: paiement BIF</h2>
    <p>Le trade <b>{trade_id}</b> est passe en <b>CRYPTO_LOCKED</b>.</p>
    <p>Montant BIF a payer: <b>{amount_bif}</b></p>
    <p>Apres paiement, cliquez sur ce lien pour confirmer:</p>
    <p><a href="{confirm_link}" style="font-weight:600;">Confirmer BIF paye</a></p>
    <p>Ce lien expire dans 12 heures.</p>
    """


async def notify_agent_fiat_confirmation_needed(db: AsyncSession, trade) -> None:
    seller_id = str(getattr(trade, "seller_id", "") or "")
    if not seller_id:
        return

    seller = await db.scalar(select(Users).where(Users.user_id == seller_id))
    seller_email = str(getattr(seller, "email", "") or "").strip()
    if not seller_email:
        return

    token = create_access_token(
        data={
            "sub": seller_id,
            "action": "p2p_fiat_sent_by_agent",
            "trade_id": str(getattr(trade, "trade_id", "")),
        },
        expires_delta=timedelta(hours=12),
    )
    link = _build_agent_confirm_link(str(trade.trade_id), token)
    amount_bif = str(getattr(trade, "bif_amount", "") or "-")
    subject = f"[P2P] Confirmation paiement BIF - Trade {trade.trade_id}"
    body_html = _build_email_html(
        trade_id=str(trade.trade_id),
        amount_bif=amount_bif,
        confirm_link=link,
    )

    try:
        # Force Mailjet for this flow (do not use Brevo here).
        mailer = MailjetEmailService(preferred_provider="mailjet")
        send_fn = partial(
            mailer.send_email,
            seller_email,
            subject,
            None,
            body_html=body_html,
            text=f"Trade {trade.trade_id}: confirmez le paiement BIF via {link}",
        )
        await anyio.to_thread.run_sync(
            send_fn,
        )
    except Exception:
        # Best effort: do not block trade status flow if email fails.
        return
