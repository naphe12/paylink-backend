import httpx
from app.config import settings

async def send_slack(message: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            settings.SLACK_WEBHOOK_URL,
            json={"text": message},
        )
