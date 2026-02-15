from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.services.system_flags import get_flag, set_flag

router = APIRouter(prefix="/admin/flags", tags=["Admin Flags"])


@router.get("/kill-switch")
async def read_kill(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    return {"key": "KILL_SWITCH", "value": await get_flag(db, "KILL_SWITCH")}


@router.post("/kill-switch")
async def set_kill(
    value: bool,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    await set_flag(db, "KILL_SWITCH", value)
    await db.commit()
    return {"key": "KILL_SWITCH", "value": value}
