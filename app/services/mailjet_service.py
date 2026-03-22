import logging

import base64
import httpx

from app.core.config import settings
from app.services.mailer import render_template

logger = logging.getLogger(__name__)


class MailjetEmailService:
    """
    Envoi d'emails via Mailjet uniquement.
    Accepte soit un template Jinja (template_name + kwargs),
    soit un contenu HTML direct (body_html), soit un texte brut (text).
    """

    def __init__(self, preferred_provider: str | None = None):
        self.mailjet_api_key = (settings.MAILJET_API_KEY or "").strip()
        self.mailjet_secret_key = (settings.MAILJET_SECRET_KEY or "").strip()
        preferred = str(preferred_provider or "").strip().lower()

        if preferred and preferred != "mailjet":
            raise ValueError("MailjetEmailService supports only Mailjet.")
        if not (self.mailjet_api_key and self.mailjet_secret_key):
            raise ValueError("MAILJET_API_KEY and MAILJET_SECRET_KEY are required.")
        self.provider = "mailjet"

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
            text = "Notification PesaPaid"

        message = {
            "From": {"Email": settings.MAIL_FROM, "Name": settings.MAIL_FROM_NAME},
            "To": [{"Email": to_email}],
            "Subject": subject,
        }
        if html_content:
            message["HTMLPart"] = html_content
        if text:
            message["TextPart"] = text
        if attachments:
            message["Attachments"] = [
                {
                    "ContentType": att.get("content_type", "application/octet-stream"),
                    "Filename": att.get("name", "document.bin"),
                    "Base64Content": base64.b64encode(att["content"]).decode("utf-8"),
                }
                for att in attachments
                if att.get("content")
            ]

        response = httpx.post(
            "https://api.mailjet.com/v3.1/send",
            json={"Messages": [message]},
            auth=(self.mailjet_api_key, self.mailjet_secret_key),
            timeout=15.0,
        )

        try:
            logger.info("Email provider=%s to=%s status=%s", self.provider, to_email, response.status_code)
        except Exception:
            pass

        if response.is_error:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"Email send failed via {self.provider}: {detail}")

        print(f"[{self.provider}] email sent? status={response.status_code} to={to_email}")
        print(response.json())
        return {"status": response.status_code, "response": response.json()}
