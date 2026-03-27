from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ChatStatus = Literal["NEED_INFO", "CONFIRM", "DONE", "ERROR", "CANCELLED"]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    target_user_id: UUID | None = None


class TransferDraft(BaseModel):
    intent: Literal["external_transfer", "capacity"] = "external_transfer"
    amount: Decimal | None = None
    currency: str | None = None
    recipient: str | None = None
    recipient_phone: str | None = None
    partner_name: str | None = None
    country_destination: str | None = None
    recognized_beneficiary: bool = False
    wallet_currency: str | None = None
    raw_message: str


class ChatResponse(BaseModel):
    status: ChatStatus
    message: str
    data: TransferDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None


class ConfirmChatRequest(BaseModel):
    draft: TransferDraft
