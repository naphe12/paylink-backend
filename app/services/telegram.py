import httpx
from typing import Optional

TELEGRAM_TOKEN = "7783929317:AAEpzVdadSTJmmNdq1UMvFrQyHzhfOu-mRI"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

async def get_chat_id() -> Optional[int]:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/getUpdates")
        data = response.json()
        try:
            return data["result"][0]["message"]["chat"]["id"]
        except (IndexError, KeyError):
            return None

async def send_message(chat_id: int, message: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/sendMessage",
            data={"chat_id": chat_id, "text": message}
        )
        return response.json()