from functools import lru_cache
from redis.asyncio import Redis
from app.config import settings

@lru_cache()
def get_redis() -> Redis | None:
    if not getattr(settings, "REDIS_URL", None):
        return None
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)

