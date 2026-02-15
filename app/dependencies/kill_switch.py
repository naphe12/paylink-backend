from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.system_flags import get_flag


async def require_not_killed(db: AsyncSession = Depends(get_db)):
    if await get_flag(db, "KILL_SWITCH"):
        raise HTTPException(503, "Service temporarily disabled")
