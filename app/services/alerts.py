import inspect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notifications
from app.models.users import Users
from app.ws.admin_ws import admin_ws

ADMIN_ROLES = {"admin", "agent"}


async def _admin_users(db: AsyncSession):
    stmt = select(Users).where(Users.role.in_(tuple(ADMIN_ROLES)))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def deliver_alerts(
    db: AsyncSession,
    subject: str,
    message: str,
    metadata: dict,
):
    admins = await _admin_users(db)

    # 1) Persist notification rows
    for u in admins:
        db.add(
            Notifications(
                user_id=u.user_id,
                channel="SYSTEM_ALERT",
                subject=subject,
                message=message,
                metadata_=metadata,
            )
        )
    await db.flush()

    # 2) Trigger actual sends (stubs for provider wiring)
    for u in admins:
        if getattr(u, "email", None):
            maybe = send_email(u.email, subject, message)
            if inspect.isawaitable(maybe):
                await maybe
        if getattr(u, "phone_e164", None):
            maybe = send_whatsapp(u.phone_e164, message)
            if inspect.isawaitable(maybe):
                await maybe
        maybe = send_slack(subject, message, metadata)
        if inspect.isawaitable(maybe):
            await maybe

    await admin_ws.broadcast(
        {
            "type": "ALERT",
            "subject": subject,
            "message": message,
            "metadata": metadata,
        }
    )


async def send_email(to_email: str, subject: str, message: str):
    # TODO: integrate your provider (Mailjet/Brevo/Sendgrid)
    return


async def send_whatsapp(to_phone: str, message: str):
    # TODO: integrate WhatsApp provider (Twilio/Meta Cloud API)
    return


async def send_slack(subject: str, message: str, metadata: dict):
    # TODO: Slack webhook
    return
