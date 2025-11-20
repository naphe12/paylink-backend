from fastapi import APIRouter
from services.telegram import get_chat_id, send_message
# routers/telegram.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from models.telegram_user import TelegramUser
from sqlalchemy.future import select
from services.telegram import get_chat_id

router = APIRouter()

@router.get("/telegram/chat-id")
async def fetch_chat_id():
    chat_id = await get_chat_id()
    if chat_id:
        return {"chat_id": chat_id}
    return {"error": "Aucun message reçu par le bot"}

@router.post("/telegram/send")
async def send_telegram_message(message: str):
    chat_id = await get_chat_id()
    if not chat_id:
        return {"error": "Impossible d’envoyer le message, chat_id introuvable"}
    result = await send_message(chat_id, message)
    return result





@router.post("/telegram/register")
async def register_user(db: AsyncSession = Depends(get_db)):
    chat_id = await get_chat_id()
    if not chat_id:
        return {"error": "Aucun message reçu par le bot"}

    # Vérifie si déjà enregistré
    result = await db.execute(select(TelegramUser).where(TelegramUser.chat_id == str(chat_id)))
    existing = result.scalar_one_or_none()
    if existing:
        return {"message": "Utilisateur déjà enregistré", "chat_id": chat_id}

    user = TelegramUser(chat_id=str(chat_id))
    db.add(user)
    await db.commit()
    return {"message": "Utilisateur enregistré", "chat_id": chat_id}

@router.post("/telegram/broadcast")
async def broadcast_message(message: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramUser))
    users = result.scalars().all()

    from services.telegram import send_message
    responses = []
    for user in users:
        res = await send_message(int(user.chat_id), message)
        responses.append({user.chat_id: res})

    return {"status": "broadcasted", "results": responses}