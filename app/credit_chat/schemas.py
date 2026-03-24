from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


CreditChatStatus = Literal["NEED_INFO", "CONFIRM", "INFO", "ERROR", "CANCELLED"]
CreditIntent = Literal["capacity", "simulate_transfer", "pending_reason", "unknown"]


class CreditChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class CreditDraft(BaseModel):
    intent: CreditIntent = "unknown"
    amount: Decimal | None = None
    currency: str | None = None
    wallet_currency: str | None = None
    raw_message: str


class CreditChatResponse(BaseModel):
    status: CreditChatStatus
    message: str
    data: CreditDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None


class ConfirmCreditChatRequest(BaseModel):
    draft: CreditDraft
