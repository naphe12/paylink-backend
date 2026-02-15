from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.services.metrics import snapshot

router = APIRouter(prefix="/admin", tags=["Metrics"])


@router.get("/metrics")
async def metrics(me: Users = Depends(get_current_admin)):
    return snapshot()
