from decimal import Decimal

from app.config import settings


class P2PMMQuote:
    @staticmethod
    def quote_price(base_price_bif_per_usd: Decimal, side: str) -> Decimal:
        """
        side = "BUY" (client wants to buy token) => PayLink sells => slightly higher price
        side = "SELL" (client wants to sell token) => PayLink buys => slightly lower price
        """
        spread = Decimal(settings.P2P_MM_SPREAD_BPS) / Decimal("10000")
        if side == "BUY":
            return base_price_bif_per_usd * (Decimal("1") + spread)
        return base_price_bif_per_usd * (Decimal("1") - spread)
