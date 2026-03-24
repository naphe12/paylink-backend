from typing import Literal

from pydantic import BaseModel, Field


WalletChatStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
WalletIntent = Literal["balance", "limits", "recent_activity", "account_status", "unknown"]


class WalletChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class WalletDraft(BaseModel):
    intent: WalletIntent = "unknown"
    raw_message: str


class WalletChatResponse(BaseModel):
    status: WalletChatStatus
    message: str
    data: WalletDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
