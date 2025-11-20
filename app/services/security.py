# app/services/security.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.models.users import Users
from app.services.aml import add_security_event
from app.websocket_manager_security import security_push

async def freeze_user(db: AsyncSession, user_id: str, reason: str):
    await db.execute(update(Users).where(Users.user_id==user_id)
                     .values(status="frozen"))
    await add_security_event(db, user_id, "high", "user_frozen", reason)
    await db.commit()
    await security_push({"type":"user_frozen","user_id":user_id,"reason":reason})

async def unfreeze_user(db: AsyncSession, user_id: str, note: str):
    await db.execute(update(Users).where(Users.user_id==user_id)
                     .values(status="active"))
    await add_security_event(db, user_id, "info", "user_unfrozen", note)
    await db.commit()
    await security_push({"type":"user_unfrozen","user_id":user_id,"note":note})
