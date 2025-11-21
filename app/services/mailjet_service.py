from mailjet_rest import Client
from app.core.config import settings

class MailjetEmailService:
    def __init__(self):
        self.client = Client(
            auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY),
            version='v3.1'
        )

    def send_email(self, to_email: str, subject: str, text: str):
        data = {
            'Messages': [
                {
                    "From": {
                        "Email": settings.MAIL_FROM,
                        "Name": settings.MAIL_FROM_NAME
                    },
                    "To": [{"Email": to_email}],
                    "Subject": subject,
                    "TextPart": text,
                }
            ]
        }

        result = self.client.send.create(data=data)
        return {"status": result.status_code, "response": result.json()}
