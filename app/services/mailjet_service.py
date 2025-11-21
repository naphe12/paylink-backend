from mailjet_rest import Client

from app.core.config import settings
from app.services.mailer import render_template


class MailjetEmailService:
    """
    Service d'envoi via Mailjet.
    Accepte soit un template Jinja (template_name + kwargs),
    soit un contenu HTML direct (body_html), soit un texte brut (text).
    """

    def __init__(self):
        self.client = Client(
            auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY),
            version="v3.1",
        )

    def send_email(
        self,
        to_email: str,
        subject: str,
        template_name: str | None = None,
        *,
        body_html: str | None = None,
        text: str | None = None,
        **kwargs,
    ):
        # Résolution du contenu HTML via template si fourni
        html_content = body_html
        if template_name:
            html_content = render_template(template_name, **kwargs)

        if html_content is None and text is None:
            raise ValueError("send_email requires template_name, body_html or text")

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": settings.MAIL_FROM,
                        "Name": settings.MAIL_FROM_NAME,
                    },
                    "To": [{"Email": to_email}],
                    "Subject": subject,
                }
            ]
        }

        if text:
            data["Messages"][0]["TextPart"] = text
        if html_content:
            data["Messages"][0]["HTMLPart"] = html_content

        result = self.client.send.create(data=data)
        return {"status": result.status_code, "response": result.json()}
