from typing import Protocol


class PayoutProvider(Protocol):
    name: str

    async def send_payout(
        self,
        *,
        amount_bif: float,
        account_number: str,
        account_name: str | None,
        reference: str,
    ) -> dict: ...

