from decimal import Decimal


class MarketMaker:
    SPREAD = Decimal("0.008")  # 0.8%

    @staticmethod
    def buy_price(base_price: Decimal):
        return base_price * (Decimal("1") + MarketMaker.SPREAD)

    @staticmethod
    def sell_price(base_price: Decimal):
        return base_price * (Decimal("1") - MarketMaker.SPREAD)
