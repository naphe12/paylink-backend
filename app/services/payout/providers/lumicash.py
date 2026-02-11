class LumicashProvider:
    name = "LUMICASH"

    async def send_payout(
        self,
        *,
        amount_bif: float,
        account_number: str,
        account_name: str | None,
        reference: str,
    ) -> dict:
        # TODO: call API lumicash
        return {
            "ok": True,
            "reference": reference,
            "amount_bif": amount_bif,
            "account_number": account_number,
            "account_name": account_name,
        }

