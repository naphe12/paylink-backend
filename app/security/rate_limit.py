import time
from fastapi import HTTPException, Request
from app.config import settings
from app.security.redis_client import get_redis

async def rate_limit(request: Request, key: str, limit: int, window_seconds: int):
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return
    r = get_redis()
    if not r:
        return  # pas de redis => pas de RL (ou tu peux lever)

    now = int(time.time())
    window = now // window_seconds
    redis_key = f"rl:{key}:{window}"

    count = await r.incr(redis_key)
    if count == 1:
        await r.expire(redis_key, window_seconds + 5)

    if count > limit:
        raise HTTPException(429, "Too many requests")
