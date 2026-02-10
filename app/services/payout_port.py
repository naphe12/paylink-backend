from dataclasses import dataclass
from typing import Protocol

@dataclass
class PayoutResult:
    reference: str
    provider_status: str

class PayoutProvider(Protocol):
    async def send_bif(self, amount_bif: float, destination: dict) -> PayoutResult: ...
