from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.agents import Agents
from app.models.users import Users
from app.services.mailjet_service import MailjetEmailService

router = APIRouter(tags=["Debug"])


@router.get("/debug/email/config")
def debug_email_config():
    return {
        "mail_provider": getattr(settings, "MAIL_PROVIDER", None),
        "mail_from": getattr(settings, "MAIL_FROM", None),
        "mail_from_name": getattr(settings, "MAIL_FROM_NAME", None),
        "has_resend_api_key": bool(str(getattr(settings, "RESEND_API_KEY", "") or "").strip()),
        "has_brevo_api_key": bool(str(getattr(settings, "BREVO_API_KEY", "") or "").strip()),
        "has_mailjet_api_key": bool(str(getattr(settings, "MAILJET_API_KEY", "") or "").strip()),
        "has_mailjet_secret_key": bool(str(getattr(settings, "MAILJET_SECRET_KEY", "") or "").strip()),
        "smtp_host": getattr(settings, "SMTP_HOST", None),
        "smtp_port": getattr(settings, "SMTP_PORT", None),
        "has_smtp_user": bool(str(getattr(settings, "SMTP_USER", "") or "").strip()),
        "has_smtp_pass": bool(str(getattr(settings, "SMTP_PASS", "") or "").strip()),
    }


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
        Users.email,
        Agents.active,
    ).outerjoin(Users, Users.user_id == Agents.user_id).where(
        or_(
            Agents.email.is_not(None),
            Users.email.is_not(None),
        )
    ).order_by(Agents.display_name.asc())
    if active_only:
        stmt = stmt.where(Agents.active.is_(True))
    rows = (await db.execute(stmt)).all()
    seen = set()
    payload = []
    for agent_id, user_id, display_name, agent_email, user_email, active in rows:
        normalized_agent = str(agent_email or "").strip().lower()
        normalized_user = str(user_email or "").strip().lower()
        normalized = normalized_agent or normalized_user
        duplicate_of = normalized if normalized and normalized in seen else None
        if normalized:
            seen.add(normalized)
        payload.append(
            {
                "agent_id": str(agent_id),
                "user_id": str(user_id) if user_id else None,
                "display_name": display_name,
                "agent_email": agent_email,
                "user_email": user_email,
                "email_used": normalized or None,
                "email_source": (
                    "agents.email"
                    if normalized_agent
                    else "users.email"
                    if normalized_user
                    else None
                ),
                "normalized_email": normalized or None,
                "active": bool(active),
                "would_receive_notification": bool(active) and bool(normalized) and duplicate_of is None,
                "excluded_reason": (
                    None
                    if (bool(active) and bool(normalized) and duplicate_of is None)
                    else (
                        "duplicate_email"
                        if duplicate_of is not None
                        else "missing_email"
                        if not normalized
                        else "inactive"
                    )
                ),
            }
        )
    return payload


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
        Users.email,
        Agents.active,
    ).outerjoin(Users, Users.user_id == Agents.user_id).where(
        or_(
            Agents.email.is_not(None),
            Users.email.is_not(None),
        )
    ).order_by(Agents.display_name.asc())
    if active_only:
        stmt = stmt.where(Agents.active.is_(True))
    rows = (await db.execute(stmt)).all()

    recipients = []
    seen = set()
    skipped = []
    for display_name, agent_email, user_email, active in rows:
        normalized_agent = str(agent_email or "").strip().lower()
        normalized_user = str(user_email or "").strip().lower()
        normalized = normalized_agent or normalized_user
        source = (
            "agents.email"
            if normalized_agent
            else "users.email"
            if normalized_user
            else None
        )
        if not normalized:
            skipped.append(
                {
                    "display_name": display_name,
                    "agent_email": agent_email,
                    "user_email": user_email,
                    "active": bool(active),
                    "reason": "missing_email",
                }
            )
            continue
        if normalized in seen:
            skipped.append(
                {
                    "display_name": display_name,
                    "email": normalized,
                    "agent_email": agent_email,
                    "user_email": user_email,
                    "active": bool(active),
                    "reason": "duplicate_email",
                }
            )
            continue
        seen.add(normalized)
        recipients.append(
            {
                "display_name": display_name,
                "email": normalized,
                "source": source,
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
            "skipped": skipped,
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
