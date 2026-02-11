import uuid

from services.payout_port import PayoutProvider, PayoutResult


class ProviderC(PayoutProvider):
    name = "providerc"

    async def send_payout(
        self,
        *,
        amount_bif: float,
        phone: str,
        reference: str,
    ) -> dict:
        return {
            "reference": reference or f"PROVC-{uuid.uuid4()}",
            "provider_status": "SENT",
            "amount_bif": amount_bif,
            "phone": phone,
        }

    async def send_bif(self, amount_bif: float, destination: dict) -> PayoutResult:
        ref = f"PROVC-{uuid.uuid4()}"
        payload = await self.send_payout(
            amount_bif=amount_bif,
            phone=str(destination.get("account") or ""),
            reference=ref,
        )
        return PayoutResult(
            reference=str(payload.get("reference") or ref),
            provider_status=str(payload.get("provider_status") or "SENT"),
        )
