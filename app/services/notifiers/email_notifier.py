from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from app.services.mailer import send_email
from app.services.notifiers.base import NotificationMessage


class EmailNotifier:
    async def notify(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
    ) -> None:
        body_html = message.body_html or f"<p>{message.body_text}</p>"
        await run_in_threadpool(
            send_email,
            recipient,
            message.subject,
            None,
            body_html=body_html,
        )

