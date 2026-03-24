from typing import Literal

from pydantic import BaseModel, Field


EscrowChatStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
EscrowChatIntent = Literal["latest_status", "why_pending", "next_step", "track_order", "unknown"]


class EscrowChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class EscrowDraft(BaseModel):
    intent: EscrowChatIntent = "unknown"
    order_id: str | None = None
    raw_message: str


class EscrowChatResponse(BaseModel):
    status: EscrowChatStatus
    message: str
    data: EscrowDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
