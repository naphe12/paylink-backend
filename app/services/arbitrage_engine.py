import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.idempotency import IdempotencyKeys
from app.services.audit import audit
from app.services.circuit_breaker import BreakerConfig, CircuitBreaker


class ArbitrageEngine:
    def __init__(self):
        self.breaker = CircuitBreaker(
            "arbitrage",
            settings.REDIS_URL,
            BreakerConfig(
                settings.CB_FAIL_THRESHOLD,
                settings.CB_OPEN_SECONDS,
                settings.CB_HALFOPEN_MAX_CALLS,
            ),
        )

    @staticmethod
    def make_key(plan: dict) -> str:
        payload = json.dumps(plan, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def execute_plan(
        self,
        db: AsyncSession,
        plan: dict,
        actor_user_id=None,
        actor_role="SYSTEM",
    ):
        """
        plan example:
        {
          "pair": "USDC/USDT",
          "amount_usd": "500",
          "min_profit_usd": "2.0",
          "legs": [...]
        }
        """
        if not await self.breaker.allow():
            raise RuntimeError("Arbitrage breaker OPEN")

        key = self.make_key(plan)

        # idempotency
        key_col = getattr(IdempotencyKeys, "key", None) or getattr(IdempotencyKeys, "client_key")
        exists = await db.scalar(select(IdempotencyKeys).where(key_col == key))
        if exists:
            cached_response = getattr(exists, "response", None)
            if cached_response is not None:
                return cached_response
            return {"status": "IDEMPOTENT_REPLAY", "key": key}

        # bounded safety checks
        amount = Decimal(str(plan.get("amount_usd", "0")))
        min_profit = Decimal(str(plan.get("min_profit_usd", "0")))
        if amount <= 0 or amount > Decimal("5000"):
            raise ValueError("amount out of bounds")
        if min_profit < Decimal("0.5"):
            raise ValueError("min_profit too low")

        try:
            # TODO: execute legs (swap_engine / external)
            result = {"status": "EXECUTED", "key": key}

            idem_payload = {}
            if hasattr(IdempotencyKeys, "key"):
                idem_payload["key"] = key
            if hasattr(IdempotencyKeys, "client_key"):
                idem_payload["client_key"] = key
            if hasattr(IdempotencyKeys, "scope"):
                idem_payload["scope"] = "ARBITRAGE"
            if hasattr(IdempotencyKeys, "response"):
                idem_payload["response"] = result

            db.add(IdempotencyKeys(**idem_payload))

            await audit(
                db,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="ARBITRAGE_EXECUTED",
                entity_type="ARBITRAGE",
                entity_id=None,
                metadata={"plan": plan, "result": result},
            )

            await self.breaker.record_success()
            await db.commit()
            return result
        except Exception as e:
            await self.breaker.record_failure()
            await audit(
                db,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="ARBITRAGE_FAILED",
                entity_type="ARBITRAGE",
                entity_id=None,
                metadata={"plan": plan, "error": str(e)},
            )
            await db.commit()
            raise
