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
        account_number: str,
        account_name: str | None,
        reference: str,
    ) -> dict:
        last_exc: Exception | None = None

        for provider in self.providers:
            key = f"PAYOUT_CIRCUIT_{provider.name}"
            if not await circuit_allow(db, key):
                continue
            try:
                resp = await provider.send_payout(
                    amount_bif=amount_bif,
                    account_number=account_number,
                    account_name=account_name,
                    reference=reference,
                )
                await circuit_success(db, key)
                return {"provider": provider.name, "provider_response": resp}
            except Exception as exc:
                last_exc = exc
                await circuit_failure(db, key)

        raise last_exc or Exception("No payout provider available")

