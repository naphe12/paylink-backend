# app/services/agent_ops.py
from decimal import Decimal

def compute_agent_commission(amount: float, rate: Decimal | None = None) -> Decimal:
    pct = rate or Decimal("0.015")
    comm = Decimal(str(amount)) * pct
    if comm < Decimal("0.25"):
        comm = Decimal("0.25")
    return comm.quantize(Decimal("0.01"))
