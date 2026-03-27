from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TransferSupportStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
TransferSupportIntent = Literal["track_transfer", "pending_reason", "status_help", "capacity", "unknown"]


class TransferSupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    target_user_id: UUID | None = None


class TransferSupportDraft(BaseModel):
    intent: TransferSupportIntent = "unknown"
    reference_code: str | None = None
    raw_message: str
    semantic_hints: dict = Field(default_factory=dict)


class TransferSupportChatResponse(BaseModel):
    status: TransferSupportStatus
    message: str
    data: TransferSupportDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
