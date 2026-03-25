import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import TemplateNotFound
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configuration du moteur Jinja2 pour le rendu HTML
env = Environment(
    loader=FileSystemLoader('app/services/templates'),
    autoescape=select_autoescape(['html', 'xml'])
)


def render_template(template_name: str, **kwargs) -> str:
    """Rend un template HTML avec les variables fournies."""
    template = env.get_template(template_name)
    return template.render(**kwargs)


def send_email(
    to: str,
    subject: str,
    template_name: str | None = None,
    *,
    body_html: str | None = None,
    text: str | None = None,
    **kwargs,
):
    """Envoie un email via provider API (Brevo/Mailjet) avec fallback SMTP legacy."""
    html_content = body_html
    raw_text = text

    if template_name:
        try:
            html_content = render_template(template_name, **kwargs)
        except TemplateNotFound:
            # Backward compatibility for callers still passing a plain message as 3rd positional arg.
            if body_html is None:
                html_content = f"<p>{template_name}</p>"
            if raw_text is None:
                raw_text = template_name
    elif body_html is None and raw_text is not None:
        html_content = f"<p>{raw_text}</p>"

    if html_content is None and raw_text is None:
        raise ValueError("send_email requires a template, body_html or text.")

    provider_error: Exception | None = None
    try:
        from app.services.mailjet_service import MailjetEmailService

        mailer = MailjetEmailService(preferred_provider=getattr(settings, "MAIL_PROVIDER", "resend"))
        return mailer.send_email(
            to,
            subject,
            None,
            body_html=html_content,
            text=raw_text,
        )
    except Exception as exc:
        provider_error = exc
        logger.exception(
            "Primary email provider failed provider=%s to=%s",
            getattr(settings, "MAIL_PROVIDER", "resend"),
            to,
        )

    smtp_user = str(getattr(settings, "SMTP_USER", "") or "").strip()
    smtp_pass = str(getattr(settings, "SMTP_PASS", "") or "").strip()
    smtp_host = str(getattr(settings, "SMTP_HOST", "") or "").strip()
    if not (smtp_host and smtp_user and smtp_pass):
        if provider_error is not None:
            raise RuntimeError(
                f"Email provider failed and SMTP fallback is not configured: {provider_error}"
            ) from provider_error
        raise RuntimeError("SMTP fallback is not configured.")

    msg = MIMEMultipart('alternative')
    msg['From'] = settings.MAIL_FROM
    msg['To'] = to
    msg['Subject'] = subject
    if raw_text:
        msg.attach(MIMEText(raw_text, 'plain'))
    if html_content:
        msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
    except Exception as smtp_exc:
        logger.exception("SMTP fallback failed to=%s host=%s", to, settings.SMTP_HOST)
        if provider_error is not None:
            raise RuntimeError(
                f"Email delivery failed: provider error={provider_error}; smtp error={smtp_exc}"
            ) from smtp_exc
        raise

    print(f"Email '{subject}' envoye a {to}")
