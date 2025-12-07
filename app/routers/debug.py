import httpx
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["Debug"])


@router.get("/send-email")
async def send_email():
    payload = {
        "sender": {"email": "adolphe.nahimana@gmail.com", "name": "PayLink App"},
        "to": [{"email": "naphe12@yahoo.fr"}],
        "subject": "Test Brevo",
        "htmlContent": "<h1>Email envoyé¸ via Brevo ÐYZ%</h1>",
    }

    headers = {"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
        )

    return response.json()
