from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.dependencies.kill_switch import require_not_killed
from app.models.users import Users
from app.services.arbitrage_engine import ArbitrageEngine

router = APIRouter(prefix="/admin/arbitrage", tags=["Admin Arbitrage"])
engine = ArbitrageEngine()


@router.post("/execute")
async def execute(
    plan: dict,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
    _: None = Depends(require_not_killed),
):
    return await engine.execute_plan(
        db,
        plan,
        actor_user_id=me.user_id,
        actor_role=str(me.role),
    )
