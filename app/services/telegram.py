import os
from typing import Optional

import httpx

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""

async def get_chat_id() -> Optional[int]:
    if not BASE_URL:
        raise RuntimeError("TELEGRAM_BOT_TOKEN manquant")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/getUpdates")
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram getUpdates error: {data}")
        try:
            return data["result"][0]["message"]["chat"]["id"]
        except (IndexError, KeyError):
            return None

async def send_message(chat_id: int, message: str) -> dict:
    if not BASE_URL:
        raise RuntimeError("TELEGRAM_BOT_TOKEN manquant")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/sendMessage",
            data={"chat_id": str(chat_id).strip(), "text": message}
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(f"Telegram sendMessage error: {payload}")
        return payload
