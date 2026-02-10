from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.mailer import send_email


async def notify(
    db: AsyncSession,
    *,
    user_id,
    subject: str,
    message: str,
) -> None:
    row = (
        await db.execute(
            text(
                """
                SELECT email, phone_e164
                FROM paylink.users
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": str(user_id)},
        )
    ).first()

    if not row:
        return

    email = row[0]
    phone = row[1]

    if email:
        try:
            await run_in_threadpool(
                send_email,
                to=email,
                subject=subject,
                body_html=f"<p>{message}</p>",
            )
        except Exception:
            # Notification is best-effort and must not break escrow processing.
            pass

    if phone:
        # Placeholder: plug Twilio / Meta / 360dialog provider here.
        print(f"[escrow_notify_whatsapp] to={phone} subject={subject} message={message}")
