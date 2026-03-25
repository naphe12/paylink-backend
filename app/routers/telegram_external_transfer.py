from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.services.telegram_external_transfer_service import (
    build_telegram_link_token,
    process_telegram_update,
)


router = APIRouter(prefix="/telegram/external-transfer", tags=["Telegram External Transfer"])


@router.post("/link-token")
async def create_telegram_external_transfer_link_token(
    current_user: Users = Depends(get_current_user_db),
):
    payload = build_telegram_link_token(user_id=str(current_user.user_id))
    return {
        "bot_username": payload["bot_username"] or None,
        "bot_url": payload["bot_url"] or None,
        "command": payload["command"],
        "token": payload["token"],
    }


@router.post("/webhook")
async def telegram_external_transfer_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    update = await request.json()
    return await process_telegram_update(db, update)
