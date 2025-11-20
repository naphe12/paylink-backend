import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

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
    **kwargs,
):
    """Envoie un email HTML en utilisant un template ou un contenu fourni."""
    if template_name:
        html_content = render_template(template_name, **kwargs)
    elif body_html is not None:
        html_content = body_html
    else:
        raise ValueError('send_email requires a template or body_html.')

    msg = MIMEMultipart('alternative')
    msg['From'] = settings.MAIL_FROM
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)

    print(f"Email '{subject}' envoye a {to}")
