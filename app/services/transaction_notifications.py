import logging
from collections.abc import Iterable
from typing import Sequence

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction_email_recipients import TransactionEmailRecipient
from app.models.users import Users
from app.services.mailer import send_email

logger = logging.getLogger(__name__)


async def get_transaction_emails(db: AsyncSession, initiator: Users | None) -> list[str]:
    rows: Sequence[str] = await db.scalars(
        select(TransactionEmailRecipient.email).where(TransactionEmailRecipient.active.is_(True))
    )
    emails = {email for email in rows if email}
    if initiator and initiator.email:
        emails.add(initiator.email)
    return list(emails)


async def send_transaction_emails(
    db: AsyncSession,
    initiator: Users | None,
    subject: str,
    template: str | None = None,
    body: str | None = None,
    **template_kwargs,
) -> None:
    recipients = await get_transaction_emails(db, initiator)
    if not recipients:
        return

    for email in recipients:
        try:
            await run_in_threadpool(
                send_email,
                email,
                subject,
                template,
                body_html=body,
                **template_kwargs,
            )
        except Exception as exc:  # pragma: no cover
            # Ne pas bloquer la transaction en cas d'erreur SMTP / réseau.
            logger.exception("Impossible d'envoyer le mail de transaction à %s: %s", email, exc)
