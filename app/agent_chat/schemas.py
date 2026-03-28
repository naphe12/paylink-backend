from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ChatStatus = Literal["NEED_INFO", "CONFIRM", "DONE", "ERROR", "CANCELLED"]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    target_user_id: UUID | None = None


class AgentChatDraft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    intent: Literal[
        "external_transfer",
        "capacity",
        "wallet_limits",
        "transfer_status",
        "pending_reason",
        "beneficiary_add",
        "beneficiary_list",
        "kyc_status",
        "escrow_status",
    ] = "external_transfer"
    amount: Decimal | None = None
    currency: str | None = None
    recipient: str | None = None
    recipient_phone: str | None = None
    account_ref: str | None = Field(default=None, alias="recipient_email")
    partner_name: str | None = None
    country_destination: str | None = None
    recognized_beneficiary: bool = False
    beneficiary_candidates: list[dict] = Field(default_factory=list)
    selected_beneficiary_index: int | None = None
    wallet_currency: str | None = None
    reference_code: str | None = None
    order_id: str | None = None
    raw_message: str


class ChatResponse(BaseModel):
    status: ChatStatus
    message: str
    data: AgentChatDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None


class ConfirmChatRequest(BaseModel):
    draft: AgentChatDraft
