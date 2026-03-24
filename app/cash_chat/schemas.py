from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


CashChatStatus = Literal["NEED_INFO", "CONFIRM", "DONE", "INFO", "ERROR", "CANCELLED"]
CashIntent = Literal["deposit", "withdraw", "capacity", "request_status", "unknown"]


class CashChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class CashDraft(BaseModel):
    intent: CashIntent = "unknown"
    amount: Decimal | None = None
    currency: str | None = None
    mobile_number: str | None = None
    provider_name: str | None = None
    note: str | None = None
    wallet_currency: str | None = None
    raw_message: str


class CashChatResponse(BaseModel):
    status: CashChatStatus
    message: str
    data: CashDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None


class ConfirmCashChatRequest(BaseModel):
    draft: CashDraft
