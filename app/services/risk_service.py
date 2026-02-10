from decimal import Decimal

class RiskService:
    @staticmethod
    def score(usdc_amount: Decimal, confirmations: int, network: str) -> tuple[int, list[str]]:
        score = 0
        flags = []

        if usdc_amount >= Decimal("1000"):
            score += 20
            flags.append("HIGH_AMOUNT")

        if confirmations < 1:
            score += 30
            flags.append("LOW_CONFIRMATIONS")

        if network in ("OTHER", "TRON"):
            score += 10
            flags.append("RISKY_NETWORK")

        return min(score, 100), flags
