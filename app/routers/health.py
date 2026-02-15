from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db

try:
    import redis.asyncio as redis
except Exception:
    redis = None

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health():
    return {"ok": True}

@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"ok": True, "db": "ok"}

@router.get("/health/ledger")
async def health_ledger(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("""
      SELECT COUNT(*) FROM (
        SELECT journal_id
        FROM paylink.ledger_entries
        GROUP BY journal_id
        HAVING
          SUM(CASE WHEN direction='DEBIT' THEN amount ELSE 0 END)
          <>
          SUM(CASE WHEN direction='CREDIT' THEN amount ELSE 0 END)
      ) t
    """))
    bad = res.scalar_one()
    return {"ok": bad == 0, "unbalanced_journals": bad}


@router.get("/healthz")
async def healthz():
    return {"status": "ok", "env": settings.APP_ENV}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)):
    # DB check
    await db.execute(text("SELECT 1"))

    # Redis check
    if settings.REDIS_URL and redis:
        r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        pong = await r.ping()
        if not pong:
            return {"status": "fail", "redis": "no-pong"}
    return {"status": "ready"}
