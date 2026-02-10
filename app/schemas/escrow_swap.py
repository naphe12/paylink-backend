from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal

class SwapExecuteRequest(BaseModel):
    order_id: UUID
    output_amount_usdt: Decimal = Field(gt=0)
    fee_amount_usdt: Decimal = Field(ge=0)
    reference: str | None = None  # id CEX/DEX ou ref interne

from pydantic import BaseModel
from uuid import UUID
from decimal import Decimal
from datetime import datetime

class SwapExecuteResponse(BaseModel):
    order_id: UUID
    status: str
    input_amount_usdc: Decimal
    output_amount_usdt: Decimal
    fee_amount_usdt: Decimal
    executed_at: datetime

