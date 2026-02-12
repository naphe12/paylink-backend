from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import inspect
import json

from app.config import settings

try:
    from app.services.mail_service import send_email  # preferred wrapper if present
except Exception:
    try:
        from app.services.mailer import send_email  # fallback existing sync sender
    except Exception:
        send_email = None

try:
    from app.services.whatsapp_service import send_whatsapp
except Exception:
    send_whatsapp = None

try:
    from app.services.slack_service import send_slack
except Exception:
    send_slack = None

async def deliver_alerts(db: AsyncSession):
    res = await db.execute(text("""
      SELECT id, type, severity, user_id, order_id, payload
      FROM paylink.alerts
      WHERE delivered = false
      ORDER BY created_at ASC
      LIMIT 50
    """))

    alerts = [dict(r._mapping) for r in res.fetchall()]
    admin_email = getattr(settings, "ADMIN_ALERT_EMAIL", None)
    admin_phone = getattr(settings, "ADMIN_ALERT_PHONE", None)
    slack_webhook = getattr(settings, "SLACK_WEBHOOK_URL", None)

    for alert in alerts:
        payload = alert.get("payload")
        if isinstance(payload, (dict, list)):
            payload_text = json.dumps(payload, ensure_ascii=True)
        else:
            payload_text = str(payload)

        message = (
            "PAYLINK RISK ALERT\n"
            f"Type: {alert.get('type')}\n"
            f"Severity: {alert.get('severity')}\n"
            f"User: {alert.get('user_id')}\n"
            f"Order: {alert.get('order_id')}\n"
            f"Details: {payload_text}"
        )

        await db.execute(
            text(
                """
                INSERT INTO paylink.notifications (user_id, title, message, type)
                VALUES (CAST(:user_id AS uuid), :title, :message, :type)
                """
            ),
            {
                "user_id": alert.get("user_id"),
                "title": "Risk Alert",
                "message": message,
                "type": "risk_alert",
            },
        )

        if admin_email and send_email:
            try:
                maybe = send_email(
                    to=admin_email,
                    subject="[PAYLINK] Risk Alert",
                    body_html=f"<pre>{message}</pre>",
                )
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                pass

        if admin_phone and send_whatsapp:
            try:
                maybe = send_whatsapp(to=admin_phone, message=message)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                pass

        if slack_webhook and send_slack:
            try:
                maybe = send_slack(message)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                pass

        await db.execute(
            text(
                """
                UPDATE paylink.alerts
                SET delivered = true
                WHERE id = :id
                """
            ),
            {"id": alert["id"]},
        )

    await db.commit()
