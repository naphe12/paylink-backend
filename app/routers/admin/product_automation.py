from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.services.product_automation_worker import run_product_automation_cycle

router = APIRouter(prefix="/admin/ops/product-automation", tags=["Admin Product Automation"])


@router.post("/run")
async def run_product_automation_cycle_route(
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await run_product_automation_cycle(
        db,
        batch_limit=settings.PRODUCT_AUTOMATION_BATCH_LIMIT,
    )
