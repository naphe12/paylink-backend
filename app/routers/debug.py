import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings

router = APIRouter(tags=["Debug"])


@router.get("/send-email")
async def send_email():
    api_key = (settings.BREVO_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY is not configured")

    payload = {
        "sender": {"email": "adolphe.nahimana@gmail.com", "name": "PayLink App"},
        "to": [{"email": "naphe12@yahoo.fr"}],
        "subject": "Test Brevo",
        "htmlContent": "<h1>Email envoye via Brevo</h1>",
    }

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
        )

    if response.is_error:
        # Bubble up Brevo error details to help debugging bad credentials/config
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response.json()
