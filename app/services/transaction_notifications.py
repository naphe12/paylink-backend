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
    attachments: list[dict] | None = None,
    recipients: list[str] | None = None,
    **template_kwargs,
) -> None:
    target_emails = recipients or await get_transaction_emails(db, initiator, receiver)
    if not target_emails:
        logger.warning("No transaction email recipients resolved for subject=%s", subject)
        return

    mailer = MailjetEmailService(preferred_provider="brevo")
    logger.info("Sending transaction emails provider=%s subject=%s recipients=%s", mailer.provider, subject, target_emails)
    for email in target_emails:
        print(f"[{mailer.provider}] sending transaction email to={email}")
        try:
            resp = await run_in_threadpool(
                mailer.send_email,
                email,
                subject,
                template,
                body_html=body,
                attachments=attachments,
                **template_kwargs,
            )
            status = None
            try:
                status = resp.get("status")
            except Exception:
                status = None
            if status not in (200, 201):
                logger.warning("Email provider=%s responded with status=%s for %s", mailer.provider, status, email)
            else:
                print(f"[{mailer.provider}] transaction email sent status={status} to={email}")
        except Exception as exc:  # pragma: no cover
            # Ne pas bloquer la transaction en cas d'erreur SMTP / reseau.
            logger.exception("Impossible d'envoyer le mail de transaction a %s: %s", email, exc)
