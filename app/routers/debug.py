from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agents import Agents
from app.services.mailjet_service import MailjetEmailService

router = APIRouter(tags=["Debug"])


@router.get("/send-email")
def send_email_debug(
    to: str = Query(..., description="Adresse email destinataire"),
    provider: str | None = Query(
        default=None,
        description="Provider force: mailjet ou brevo. Laisser vide pour le provider par defaut.",
    ),
    subject: str = Query(default="Test email - PesaPaid"),
):
    try:
        mailer = MailjetEmailService(preferred_provider=provider)
        return mailer.send_email(
            to_email=to,
            subject=subject,
            body_html=(
                "<h1>Test d'envoi email</h1>"
                f"<p>Provider: {mailer.provider}</p>"
                f"<p>Destinataire: {to}</p>"
                "<p>Ce message provient de la route de debug PesaPaid.</p>"
            ),
            text=f"Test d'envoi email PesaPaid via {mailer.provider} vers {to}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/debug/agents/emails")
async def debug_agent_emails(
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(
        Agents.agent_id,
        Agents.user_id,
        Agents.display_name,
        Agents.email,
        Agents.active,
    ).order_by(Agents.display_name.asc())
    if active_only:
        stmt = stmt.where(Agents.active.is_(True))
    rows = (await db.execute(stmt)).all()
    return [
        {
            "agent_id": str(agent_id),
            "user_id": str(user_id) if user_id else None,
            "display_name": display_name,
            "email": email,
            "active": bool(active),
        }
        for agent_id, user_id, display_name, email, active in rows
    ]


@router.post("/debug/agents/send-email")
async def debug_send_email_to_agents(
    subject: str = Query(default="Test email agents - PesaPaid"),
    provider: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(
        Agents.display_name,
        Agents.email,
        Agents.active,
    ).order_by(Agents.display_name.asc())
    if active_only:
        stmt = stmt.where(Agents.active.is_(True))
    rows = (await db.execute(stmt)).all()

    recipients = []
    seen = set()
    for display_name, email, active in rows:
        normalized = str(email or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(
            {
                "display_name": display_name,
                "email": normalized,
                "active": bool(active),
            }
        )

    if not recipients:
        raise HTTPException(status_code=404, detail="Aucun agent email trouve.")

    try:
        mailer = MailjetEmailService(preferred_provider=provider)
        results = []
        for recipient in recipients:
            resp = mailer.send_email(
                to_email=recipient["email"],
                subject=subject,
                body_html=(
                    "<h1>Test email agents</h1>"
                    f"<p>Provider: {mailer.provider}</p>"
                    f"<p>Agent: {recipient['display_name']}</p>"
                    f"<p>Email: {recipient['email']}</p>"
                    "<p>Ce message provient de la route debug agents.</p>"
                ),
                text=(
                    f"Test email agents via {mailer.provider} "
                    f"pour {recipient['display_name']} <{recipient['email']}>"
                ),
            )
            results.append(
                {
                    "display_name": recipient["display_name"],
                    "email": recipient["email"],
                    "status": resp.get("status"),
                }
            )
        return {
            "provider": mailer.provider,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
