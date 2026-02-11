from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.get("/env")
def get_env():
    return {
        "env": settings.APP_ENV,
        "sandbox_enabled": settings.SANDBOX_ENABLED,
    }
