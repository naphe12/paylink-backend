from typing import Literal
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


WalletChatStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
WalletIntent = Literal[
    "balance",
    "limits",
    "recent_activity",
    "account_status",
    "explain_movements_on_date",
    "unknown",
]


class WalletChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    target_user_id: UUID | None = None


class WalletDraft(BaseModel):
    intent: WalletIntent = "unknown"
    raw_message: str
    target_date: date | None = None
    scope: Literal["wallet", "credit_line", "both"] = "both"


class WalletChatResponse(BaseModel):
    status: WalletChatStatus
    message: str
    data: WalletDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
