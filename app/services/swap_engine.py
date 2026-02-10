from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

@dataclass
class SwapResult:
    output_amount_usdt: Decimal
    fee_amount_usdt: Decimal
    reference: str | None = None
    rate: Decimal | None = None  # usdt/usdc

class SwapProvider(Protocol):
    async def swap_usdc_to_usdt(self, usdc_amount: Decimal) -> SwapResult:
        ...

class InternalInventorySwapProvider:
    """
    Mode MVP: PayLink dispose d'un inventaire USDT et 'vend' des USDT en échange des USDC.
    Ici, on ne touche pas à la blockchain: c'est une conversion comptable + trésorerie interne.
    """
    def __init__(self, rate_usdc_usdt: Decimal = Decimal("1.0"), fee_pct: Decimal = Decimal("0.002")):
        self.rate = rate_usdc_usdt
        self.fee_pct = fee_pct

    async def swap_usdc_to_usdt(self, usdc_amount: Decimal) -> SwapResult:
        gross = (usdc_amount * self.rate)
        fee = (gross * self.fee_pct).quantize(Decimal("0.00000001"))
        net = (gross - fee).quantize(Decimal("0.00000001"))
        return SwapResult(
            output_amount_usdt=net,
            fee_amount_usdt=fee,
            reference="INVENTORY_INTERNAL",
            rate=self.rate,
        )
