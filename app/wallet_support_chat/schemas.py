from typing import Literal

from pydantic import BaseModel, Field


WalletSupportStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
WalletSupportIntent = Literal[
    "balance_drop",
    "missing_deposit",
    "blocked_withdraw",
    "frozen_account",
    "cant_send",
    "latest_movement",
    "unknown",
]


class WalletSupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class WalletSupportDraft(BaseModel):
    intent: WalletSupportIntent = "unknown"
    raw_message: str


class WalletSupportChatResponse(BaseModel):
    status: WalletSupportStatus
    message: str
    data: WalletSupportDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
