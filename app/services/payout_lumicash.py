import uuid
from services.payout_port import PayoutProvider, PayoutResult

class LumicashProvider(PayoutProvider):
    async def send_bif(self, amount_bif: float, destination: dict) -> PayoutResult:
        # TODO: remplacer par appel API réel
        return PayoutResult(
            reference=f"LUMI-{uuid.uuid4()}",
            provider_status="SENT",
        )
