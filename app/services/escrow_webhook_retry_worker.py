from sqlalchemy.ext.asyncio import AsyncSession

from services.escrow_webhook_service import retry_failed_webhooks


async def run_escrow_webhook_retry_worker(db: AsyncSession) -> None:
    await retry_failed_webhooks(db)
