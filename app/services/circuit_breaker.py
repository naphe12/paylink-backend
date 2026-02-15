import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings

try:
    import redis.asyncio as redis
except Exception:
    redis = None


DEFAULT_PAYOUT_CIRCUIT_KEY = "PAYOUT_CIRCUIT"


@dataclass
class BreakerConfig:
    fail_threshold: int = 5
    open_seconds: int = 60
    halfopen_max_calls: int = 3


class CircuitBreaker:
    """
    Redis storage:
      cb:{name}:state = CLOSED|OPEN|HALF
      cb:{name}:fail = int
      cb:{name}:open_until = epoch
      cb:{name}:half_calls = int
    """

    def __init__(self, name: str, redis_url: Optional[str], cfg: BreakerConfig):
        self.name = name
        self.redis_url = redis_url
        self.cfg = cfg
        self.r = None

    async def _redis(self):
        if self.r:
            return self.r
        if not self.redis_url or not redis:
            return None
        self.r = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        return self.r

    async def allow(self) -> bool:
        r = await self._redis()
        if not r:
            return True  # no breaker without redis

        state = await r.get(f"cb:{self.name}:state") or "CLOSED"
        if state == "OPEN":
            open_until = float(await r.get(f"cb:{self.name}:open_until") or "0")
            if time.time() >= open_until:
                await r.set(f"cb:{self.name}:state", "HALF")
                await r.set(f"cb:{self.name}:half_calls", "0")
                return True
            return False

        if state == "HALF":
            half_calls = int(await r.get(f"cb:{self.name}:half_calls") or "0")
            if half_calls >= self.cfg.halfopen_max_calls:
                return False
            await r.incr(f"cb:{self.name}:half_calls")
            return True

        return True  # CLOSED

    async def record_success(self):
        r = await self._redis()
        if not r:
            return
        await r.set(f"cb:{self.name}:state", "CLOSED")
        await r.set(f"cb:{self.name}:fail", "0")
        await r.set(f"cb:{self.name}:half_calls", "0")

    async def record_failure(self):
        r = await self._redis()
        if not r:
            return
        fails = int(await r.incr(f"cb:{self.name}:fail"))
        if fails >= self.cfg.fail_threshold:
            await r.set(f"cb:{self.name}:state", "OPEN")
            await r.set(f"cb:{self.name}:open_until", str(time.time() + self.cfg.open_seconds))


def _cfg() -> BreakerConfig:
    return BreakerConfig(
        fail_threshold=int(settings.CB_FAIL_THRESHOLD),
        open_seconds=int(settings.CB_OPEN_SECONDS),
        halfopen_max_calls=int(settings.CB_HALFOPEN_MAX_CALLS),
    )


def _breaker(name: str) -> CircuitBreaker:
    return CircuitBreaker(name=name, redis_url=settings.REDIS_URL, cfg=_cfg())


# Backward-compatible function API used in existing payout/provider code.
async def circuit_allow(db, key: str) -> bool:  # noqa: ARG001
    return await _breaker(key).allow()


async def circuit_success(db, key: str):  # noqa: ARG001
    await _breaker(key).record_success()


async def circuit_failure(db, key: str):  # noqa: ARG001
    await _breaker(key).record_failure()


async def get_circuit(db, key: str) -> dict:  # noqa: ARG001
    br = _breaker(key)
    r = await br._redis()
    if not r:
        return {"state": "CLOSED", "failures": 0, "open_until": None, "half_calls": 0}
    return {
        "state": await r.get(f"cb:{key}:state") or "CLOSED",
        "failures": int(await r.get(f"cb:{key}:fail") or "0"),
        "open_until": await r.get(f"cb:{key}:open_until"),
        "half_calls": int(await r.get(f"cb:{key}:half_calls") or "0"),
    }


async def set_circuit(db, key: str, value: dict):  # noqa: ARG001
    br = _breaker(key)
    r = await br._redis()
    if not r:
        return
    if "state" in value:
        await r.set(f"cb:{key}:state", str(value["state"]))
    if "failures" in value:
        await r.set(f"cb:{key}:fail", str(int(value["failures"])))
    if "open_until" in value:
        v = value["open_until"]
        await r.set(f"cb:{key}:open_until", "" if v is None else str(v))
    if "half_calls" in value:
        await r.set(f"cb:{key}:half_calls", str(int(value["half_calls"])))


async def get_payout_circuit(db) -> dict:
    return await get_circuit(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def set_payout_circuit(db, value: dict):
    await set_circuit(db, DEFAULT_PAYOUT_CIRCUIT_KEY, value)


async def circuit_allow_payout(db) -> bool:
    return await circuit_allow(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def circuit_on_success(db):
    await circuit_success(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def circuit_on_failure(db):
    await circuit_failure(db, DEFAULT_PAYOUT_CIRCUIT_KEY)
