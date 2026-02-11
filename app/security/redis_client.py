from functools import lru_cache
from app.config import settings

try:
    from redis.asyncio import Redis
except Exception:  # redis package not installed in some environments
    Redis = None  # type: ignore[assignment]

@lru_cache()
def get_redis():
    if not getattr(settings, "REDIS_URL", None):
        return None
    if Redis is None:
        return None
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)

