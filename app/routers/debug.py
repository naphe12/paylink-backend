from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/env")
def debug_env():
    return {
        "SECRET_KEY": settings.SECRET_KEY,
        "SMTP_HOST": settings.SMTP_HOST,
        "FRONTEND_URL": settings.FRONTEND_URL,
    }
