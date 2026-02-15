from decimal import Decimal


class P2PFeeEngine:
    @staticmethod
    def compute(
        token_amount: Decimal,
        price_bif_per_usd: Decimal,
        risk_score: int,
        user_tier: int = 0,
        token: str | None = None,
    ) -> dict:
        """
        Retour:
        - fee_rate (ex: 0.008 = 0.8%)
        - fee_token (fee en token)
        - fee_bif (equivalent BIF)
        """
        base = Decimal("0.008")  # 0.8%

        # token-specific tweak
        token_code = str(token or "").upper()
        if token_code == "USDT":
            base += Decimal("0.0005")

        # volume discount
        if token_amount >= Decimal("500"):
            base -= Decimal("0.001")
        if token_amount >= Decimal("2000"):
            base -= Decimal("0.002")

        # tier discount
        if user_tier >= 2:
            base -= Decimal("0.001")

        # risk surcharge
        if risk_score >= 80:
            base += Decimal("0.010")  # +1%
        elif risk_score >= 60:
            base += Decimal("0.004")

        # clamp
        if base < Decimal("0.002"):
            base = Decimal("0.002")
        if base > Decimal("0.03"):
            base = Decimal("0.03")

        fee_token = (token_amount * base).quantize(Decimal("0.00000001"))
        fee_bif = (fee_token * price_bif_per_usd).quantize(Decimal("0.01"))

        return {
            "fee_rate": str(base),
            "fee_token": str(fee_token),
            "fee_bif": str(fee_bif),
        }
