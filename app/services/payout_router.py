from sqlalchemy.ext.asyncio import AsyncSession

from app.services.circuit_breaker import circuit_allow, circuit_failure, circuit_success


class PayoutRouter:
    def __init__(self, providers: list):
        self.providers = providers

    async def send_with_failover(
        self,
        db: AsyncSession,
        *,
        amount_bif: float,
        phone: str,
        reference: str,
    ) -> dict:
        last_exc = None
        for provider in self.providers:
            provider_name = str(getattr(provider, "name", "") or "unknown")
            circuit_key = f"PAYOUT_CIRCUIT_{provider_name.upper()}"
            if not await circuit_allow(db, circuit_key):
                continue

            try:
                resp = await provider.send_payout(
                    amount_bif=amount_bif,
                    phone=phone,
                    reference=reference,
                )
                await circuit_success(db, circuit_key)
                return {"provider": provider_name, "response": resp}
            except Exception as exc:
                last_exc = exc
                await circuit_failure(db, circuit_key)
                continue

        raise last_exc or Exception("No payout provider available")
