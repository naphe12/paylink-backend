import time
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    import redis.asyncio as redis
except Exception:
    redis = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: Optional[str]):
        super().__init__(app)
        self.redis_url = redis_url
        self.r = None

    async def _get_redis(self):
        if self.r:
            return self.r
        if not self.redis_url or not redis:
            return None
        self.r = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        return self.r

    async def dispatch(self, request: Request, call_next: Callable):
        # Always let CORS preflight pass through.
        if request.method == "OPTIONS":
            return await call_next(request)

        r = await self._get_redis()
        if not r:
            return await call_next(request)  # no Redis => no rate-limit

        # key: ip + path group + minute window
        forwarded_for = request.headers.get("x-forwarded-for", "")
        real_ip = request.headers.get("x-real-ip", "")
        ip = (
            (forwarded_for.split(",")[0].strip() if forwarded_for else "")
            or real_ip
            or (request.client.host if request.client else "unknown")
        )
        path = request.url.path

        # groups (simple)
        group = "default"
        if path.startswith("/auth/"):
            group = "auth"
        elif path.startswith("/api/admin/"):
            group = "admin"
        elif path.startswith("/api/p2p/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            group = "p2p_write"
        elif path.startswith("/escrow/webhooks/"):
            group = "webhook"

        # get limits from app.state
        limits = getattr(request.app.state, "rate_limits", {})
        limit = limits.get(group, limits.get("default", 60))

        now_min = int(time.time() // 60)
        key = f"rl:{group}:{ip}:{now_min}"

        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 70)  # 70 sec (minute window)

        if count > limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded", "group": group},
                status_code=429,
            )

        return await call_next(request)
