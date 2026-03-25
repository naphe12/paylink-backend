import logging

import base64
import httpx

from app.core.config import settings
from app.services.mailer import render_template

logger = logging.getLogger(__name__)


class MailjetEmailService:
    """
    Envoi d'emails via Resend, Mailjet ou Brevo.
    Accepte soit un template Jinja (template_name + kwargs),
    soit un contenu HTML direct (body_html), soit un texte brut (text).
    """

    def __init__(self, preferred_provider: str | None = None):
        self.resend_api_key = (getattr(settings, "RESEND_API_KEY", "") or "").strip()
        self.brevo_api_key = (settings.BREVO_API_KEY or "").strip()
        self.mailjet_api_key = (settings.MAILJET_API_KEY or "").strip()
        self.mailjet_secret_key = (settings.MAILJET_SECRET_KEY or "").strip()
        configured_default = str(getattr(settings, "MAIL_PROVIDER", "") or "").strip().lower()
        preferred = str(preferred_provider or configured_default or "").strip().lower()

        if preferred in {"resend", "mailjet", "brevo"}:
            if preferred == "resend":
                if not self.resend_api_key:
                    raise ValueError("RESEND_API_KEY is required for preferred_provider=resend.")
                self.provider = "resend"
            elif preferred == "mailjet":
                if not (self.mailjet_api_key and self.mailjet_secret_key):
                    raise ValueError("MAILJET_API_KEY and MAILJET_SECRET_KEY are required for preferred_provider=mailjet.")
                self.provider = "mailjet"
            else:
                if not self.brevo_api_key:
                    raise ValueError("BREVO_API_KEY is required for preferred_provider=brevo.")
                self.provider = "brevo"
        elif self.resend_api_key:
            self.provider = "resend"
        elif self.brevo_api_key:
            self.provider = "brevo"
        elif self.mailjet_api_key and self.mailjet_secret_key:
            self.provider = "mailjet"
        else:
            raise ValueError("Configure Resend, Mailjet or Brevo credentials.")

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

        if self.provider == "resend":
            payload = {
                "from": (
                    f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
                    if getattr(settings, "MAIL_FROM_NAME", None)
                    else settings.MAIL_FROM
                ),
                "to": [to_email],
                "subject": subject,
            }
            if html_content:
                payload["html"] = html_content
            if text:
                payload["text"] = text
            if attachments:
                payload["attachments"] = [
                    {
                        "filename": att.get("name", "document.bin"),
                        "content": base64.b64encode(att["content"]).decode("utf-8"),
                    }
                    for att in attachments
                    if att.get("content")
                ]

            response = httpx.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                timeout=15.0,
            )
        elif self.provider == "brevo":
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

            response = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers={
                    "api-key": self.brevo_api_key,
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                timeout=15.0,
            )
        else:
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
            logger.error(
                "Email provider failure provider=%s to=%s sender=%s status=%s detail=%s",
                self.provider,
                to_email,
                settings.MAIL_FROM,
                response.status_code,
                detail,
            )
            raise RuntimeError(f"Email send failed via {self.provider}: {detail}")

        payload = response.json()
        logger.info(
            "Email provider success provider=%s to=%s sender=%s status=%s response=%s",
            self.provider,
            to_email,
            settings.MAIL_FROM,
            response.status_code,
            payload,
        )
        print(f"[{self.provider}] email sent? status={response.status_code} to={to_email}")
        print(payload)
        return {"status": response.status_code, "response": payload}
