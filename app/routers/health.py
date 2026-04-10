import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
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

@router.get("/version")
async def version():
    payload = {
        "ok": True,
        "env": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "commit_sha": settings.APP_COMMIT_SHA,
        "build_time": settings.APP_BUILD_TIME,
    }
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/app/version")
async def app_version():
    return await version()

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
async def healthz(request: Request, db: AsyncSession = Depends(get_db)):
    started_at_ts = float(getattr(request.app.state, "started_at_ts", time.time()))
    uptime_seconds = int(max(time.time() - started_at_ts, 0))

    db_ok = False
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    redis_ok = None
    redis_error = None
    if settings.REDIS_URL and redis:
        try:
            r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            redis_ok = bool(await r.ping())
        except Exception as exc:
            redis_ok = False
            redis_error = str(exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "env": settings.APP_ENV,
        "now_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": datetime.fromtimestamp(started_at_ts, tz=timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "pid": os.getpid(),
        "workers_started": int(len(getattr(request.app.state, "background_tasks", []) or [])),
        "checks": {
            "db": {"ok": db_ok, "error": db_error},
            "redis": {"ok": redis_ok, "error": redis_error},
        },
    }


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
