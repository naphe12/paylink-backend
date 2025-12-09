import logging

import httpx
import base64

from app.core.config import settings
from app.services.mailer import render_template

logger = logging.getLogger(__name__)


class MailjetEmailService:
    """
    Envoi d'emails via Brevo (remplace l'ancien client Mailjet).
    Accepte soit un template Jinja (template_name + kwargs),
    soit un contenu HTML direct (body_html), soit un texte brut (text).
    """

    def __init__(self):
        self.api_key = (settings.BREVO_API_KEY or "").strip()
        if not self.api_key:
            raise ValueError("BREVO_API_KEY must be configured")

    def send_email(
        self,
        to_email: str,
        subject: str,
        template_name: str | None = None,
        *,
        body_html: str | None = None,
        text: str | None = None,
        attachments: list[dict] | None = None,
        **kwargs,
    ):
        # Resolution du contenu HTML via template si fourni
        html_content = body_html
        if template_name:
            html_content = render_template(template_name, **kwargs)

        if html_content is None and text is None:
            raise ValueError("send_email requires template_name, body_html or text")

        # Ajoute un texte brut minimal si seul HTML est fourni (ameliorer la deliverabilite)
        if html_content and text is None:
            text = "Notification PayLink"

        payload = {
            "sender": {"email": settings.MAIL_FROM, "name": settings.MAIL_FROM_NAME},
            "to": [{"email": to_email}],
            "subject": subject,
        }
        if html_content:
            payload["htmlContent"] = html_content
        if text:
            payload["textContent"] = text
        if attachments:
            payload["attachment"] = [
                {
                    "content": base64.b64encode(att["content"]).decode("utf-8"),
                    "name": att.get("name", "document.pdf"),
                }
                for att in attachments
                if att.get("content")
            ]

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=15.0,
        )

        try:
            logger.info("Brevo send to %s status=%s", to_email, response.status_code)
        except Exception:
            pass

        if response.is_error:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"Brevo send failed: {detail}")

        print(f"[brevo] email sent? status={response.status_code} to={to_email}")
        print(response.json())
        return {"status": response.status_code, "response": response.json()}
