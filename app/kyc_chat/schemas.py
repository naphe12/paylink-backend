from typing import Literal

from pydantic import BaseModel, Field


KycChatStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
KycIntent = Literal["status", "missing_docs", "limits", "upgrade_benefits", "unknown"]


class KycChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class KycDraft(BaseModel):
    intent: KycIntent = "unknown"
    raw_message: str


class KycChatResponse(BaseModel):
    status: KycChatStatus
    message: str
    data: KycDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
