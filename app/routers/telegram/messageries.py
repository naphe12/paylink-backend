import httpx
from fastapi import APIRouter

router = APIRouter()

TELEGRAM_TOKEN = "7783929317:AAEpzVdadSTJmmNdq1UMvFrQyHzhfOu-mRI"
CHAT_ID = "7600938538"

@router.post("/send-telegram")
async def send_telegram(message: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message}
        )
    return {"status": "sent"}