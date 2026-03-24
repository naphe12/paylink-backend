from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


P2PChatStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
P2PChatIntent = Literal["latest_trade", "why_blocked", "next_step", "offers_summary", "track_trade", "unknown"]


class P2PChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    target_user_id: UUID | None = None


class P2PDraft(BaseModel):
    intent: P2PChatIntent = "unknown"
    trade_id: str | None = None
    raw_message: str


class P2PChatResponse(BaseModel):
    status: P2PChatStatus
    message: str
    data: P2PDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
