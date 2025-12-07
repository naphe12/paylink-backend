import logging
from typing import Sequence

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction_email_recipients import TransactionEmailRecipient
from app.models.users import Users
from app.services.mailjet_service import MailjetEmailService

logger = logging.getLogger(__name__)


async def get_transaction_emails(
    db: AsyncSession, initiator: Users | None, receiver: Users | None = None
) -> list[str]:
    rows: Sequence[str] = await db.scalars(
        select(TransactionEmailRecipient.email).where(TransactionEmailRecipient.active.is_(True))
    )
    emails = {email for email in rows if email}
    if initiator and initiator.email:
        emails.add(initiator.email)
    if receiver and receiver.email:
        emails.add(receiver.email)
    return list(emails)


async def send_transaction_emails(
    db: AsyncSession,
    initiator: Users | None,
    subject: str,
    receiver: Users | None = None,
    template: str | None = None,
    body: str | None = None,
    **template_kwargs,
) -> None:
    recipients = await get_transaction_emails(db, initiator, receiver)
    if not recipients:
        return

    mailer = MailjetEmailService()
    for email in recipients:
        print(f"[brevo] sending transaction email to={email}")
        try:
            resp = await run_in_threadpool(
                mailer.send_email,
                email,
                subject,
                template,
                body_html=body,
                **template_kwargs,
            )
            status = None
            try:
                status = resp.get("status")
            except Exception:
                status = None
            if status not in (200, 201):
                logger.warning("Mailjet responded with status=%s for %s", status, email)
            else:
                print(f"[brevo] transaction email sent status={status} to={email}")
        except Exception as exc:  # pragma: no cover
            # Ne pas bloquer la transaction en cas d'erreur SMTP / reseau.
            logger.exception("Impossible d'envoyer le mail de transaction a %s: %s", email, exc)
