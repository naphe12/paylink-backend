from twilio.rest import Client
from app.config import settings

async def send_whatsapp(to: str, message: str):
    client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)

    client.messages.create(
        from_=settings.TWILIO_WHATSAPP_NUMBER,
        body=message,
        to=f"whatsapp:{to}",
    )
