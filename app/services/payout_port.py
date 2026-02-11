from dataclasses import dataclass
from typing import Protocol

@dataclass
class PayoutResult:
    reference: str
    provider_status: str

class PayoutProvider(Protocol):
    name: str

    async def send_payout(
        self,
        *,
        amount_bif: float,
        phone: str,
        reference: str,
    ) -> dict: ...

    # Backward-compat bridge for existing callers.
    async def send_bif(self, amount_bif: float, destination: dict) -> PayoutResult: ...
